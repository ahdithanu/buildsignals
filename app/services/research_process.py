"""Local POSIX process boundary for a separately installed, trusted SDK runtime.

Interpreter, key and model arguments must come only from trusted server config,
never a request body. This is process/env isolation, not an OS, network, memory
or spend sandbox. Domain-output validation and durable audit/budgets live above it.
"""
from __future__ import annotations

import json
import math
import os
import re
import selectors
import signal
import subprocess
import time
from pathlib import Path

from agent_runtime.research import validate_bundle

_ROOT = str(Path(__file__).resolve().parents[2])
_BOOTSTRAP = (
    "import os, sys\n"
    "_allowed = ('OPENROUTER_API_KEY', 'OPENROUTER_PRIMARY_MODEL', "
    "'OPENROUTER_FALLBACK_MODELS', 'AGENT_RESEARCH_ENABLED', "
    "'ENVIRONMENT', 'OPENAI_AGENTS_DISABLE_TRACING')\n"
    "for _name in tuple(os.environ):\n"
    "    if _name not in _allowed:\n"
    "        del os.environ[_name]\n"
    "sys.path.insert(0, sys.argv[1])\n"
    "sys.argv = ['research', '--execute']\n"
    "from agent_runtime.research import main\n"
    "raise SystemExit(main())\n"
)
_MODEL = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/@+\-]{0,255}", re.ASCII)
_CODES = frozenset({
    'invalid_bundle', 'invalid_configuration', 'process_start_failed',
    'process_timeout', 'process_output_limit', 'process_failed',
    'process_io_failed', 'process_cleanup_failed', 'invalid_output',
})


class ResearchProcessError(RuntimeError):
    """Sanitized stable code; no provider, configuration or evidence text."""

    def __init__(self, code: str):
        self.code = code if code in _CODES else 'process_failed'
        super().__init__(self.code)


def _fail(code):
    failure = ResearchProcessError(code)
    try:
        raise failure from None
    finally:
        failure.__context__ = None


def _remaining(deadline):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        _fail('process_timeout')
    return remaining


def _kill_and_reap(process):
    failed = False
    try:
        # Do this even after the leader exits: descendants may retain pipe FDs.
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    except OSError:
        failed = True
    try:
        if process.poll() is None:
            process.kill()
        process.wait()
    except OSError:
        failed = True
    if failed:
        _fail('process_cleanup_failed')


def _reject_constant(_value):
    _fail('invalid_output')


def _float(value):
    result = float(value)
    if not math.isfinite(result):
        _fail('invalid_output')
    return result


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            _fail('invalid_output')
        result[key] = value
    return result


def _decode_output(output):
    try:
        result = json.loads(output.decode('utf-8'), object_pairs_hook=_object,
                            parse_constant=_reject_constant, parse_float=_float)
        if type(result) is not dict:
            _fail('invalid_output')
        return result
    except (ValueError, UnicodeError, RecursionError):
        _fail('invalid_output')


def _bounded_process(argv, env, input_bytes, timeout_seconds=75, max_output_bytes=40000) -> dict:
    """Exchange bounded output without pipe deadlock; return a strict JSON object.

    One monotonic deadline covers launch time, pipe I/O and the final child wait.
    Every exit kills the owned session's process group and reaps its direct child.
    Kernel process creation/termination itself is not interruptible by selectors.
    """
    if (os.name != 'posix' or type(argv) is not list or not argv
            or any(type(arg) is not str for arg in argv)
            or type(env) is not dict
            or any(type(key) is not str or type(value) is not str for key, value in env.items())
            or type(input_bytes) is not bytes
            or type(timeout_seconds) not in (int, float) or not math.isfinite(timeout_seconds)
            or timeout_seconds <= 0 or type(max_output_bytes) is not int or max_output_bytes < 1):
        _fail('invalid_configuration')
    deadline = time.monotonic() + timeout_seconds
    process = None
    try:
        try:
            process = subprocess.Popen(
                argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                env=env, shell=False, start_new_session=True, close_fds=True, bufsize=0,
            )
        except (OSError, ValueError):
            _fail('process_start_failed')
        _remaining(deadline)
        output = bytearray()
        offset = 0
        data = memoryview(input_bytes)
        with selectors.DefaultSelector() as selector:
            os.set_blocking(process.stdout.fileno(), False)
            os.set_blocking(process.stdin.fileno(), False)
            selector.register(process.stdout, selectors.EVENT_READ, 'stdout')
            if input_bytes:
                selector.register(process.stdin, selectors.EVENT_WRITE, 'stdin')
            else:
                process.stdin.close()
            while selector.get_map():
                for key, _mask in selector.select(_remaining(deadline)):
                    _remaining(deadline)
                    stream = key.fileobj
                    try:
                        if key.data == 'stdin':
                            offset += os.write(stream.fileno(), data[offset:offset + 16384])
                            if offset == len(data):
                                selector.unregister(stream)
                                stream.close()
                        else:
                            room = max_output_bytes - len(output)
                            chunk = os.read(stream.fileno(), min(65536, room + 1))
                            if not chunk:
                                selector.unregister(stream)
                                stream.close()
                            elif len(chunk) > room:
                                _fail('process_output_limit')
                            else:
                                output.extend(chunk)
                    except BlockingIOError:
                        continue
        try:
            returncode = process.wait(timeout=_remaining(deadline))
        except subprocess.TimeoutExpired:
            _fail('process_timeout')
        _remaining(deadline)
        if returncode != 0:
            _fail('process_failed')
        result = _decode_output(output)
        _remaining(deadline)
        return result
    except ResearchProcessError:
        raise
    except Exception:
        _fail('process_io_failed')
    finally:
        if process is not None:
            try:
                _kill_and_reap(process)
            finally:
                for stream in (process.stdin, process.stdout):
                    if stream is not None:
                        try:
                            stream.close()
                        except OSError:
                            pass


def _executable(value):
    try:
        if (type(value) is not str or not Path(value).is_absolute()
                or not Path(value).is_file() or not os.access(value, os.X_OK)):
            _fail('invalid_configuration')
    except (OSError, ValueError):
        _fail('invalid_configuration')
    return value


def _model(value):
    if type(value) is not str or not _MODEL.fullmatch(value):
        _fail('invalid_configuration')
    return value


def run_research_process(bundle: dict, *, python_executable: str, api_key: str,
                         primary_model: str, fallback_models: list[str]) -> dict:
    """Run validated saved context with trusted server-only runtime configuration."""
    try:
        validate_bundle(bundle)
        input_bytes = json.dumps(bundle, ensure_ascii=True, allow_nan=False).encode('utf-8')
        if len(input_bytes) > 20000:
            _fail('invalid_bundle')
    except (ValueError, TypeError, OverflowError, RecursionError):
        _fail('invalid_bundle')
    executable = _executable(python_executable)
    if (type(api_key) is not str or not 1 <= len(api_key) <= 4096
            or not api_key.isascii() or not api_key.isprintable() or api_key.strip() != api_key
            or type(fallback_models) is not list or len(fallback_models) > 16):
        _fail('invalid_configuration')
    env = {
        'OPENROUTER_API_KEY': api_key,
        'OPENROUTER_PRIMARY_MODEL': _model(primary_model),
        'OPENROUTER_FALLBACK_MODELS': ','.join(_model(model) for model in fallback_models),
        'AGENT_RESEARCH_ENABLED': '1',
        'ENVIRONMENT': 'development',
        'OPENAI_AGENTS_DISABLE_TRACING': '1',
    }
    return _bounded_process([executable, '-I', '-B', '-X', 'utf8', '-c', _BOOTSTRAP, _ROOT],
                            env, input_bytes)
