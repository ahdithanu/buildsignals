import json
import os
import signal
import subprocess
import sys
import time
from copy import deepcopy
from pathlib import Path

import pytest

from app.services import research_process as process

pytestmark = pytest.mark.skipif(os.name != 'posix', reason='Research process transport requires POSIX')


def bundle():
    return {'schema_version': 'research-context-v1',
            'evidence_kind': 'saved_workspace_facts_not_independently_verified',
            'evidence': [{'id': 'deal:synthetic', 'text': 'Synthetic saved facts only.'}]}


def child(code):
    return [sys.executable, '-I', '-B', '-X', 'utf8', '-c', code]


def run_child(code, data=b'{}', **kwargs):
    return process._bounded_process(child(code), {}, data, **kwargs)


def assert_error(code, call):
    with pytest.raises(process.ResearchProcessError) as error:
        call()
    assert error.value.code == code
    assert str(error.value) == code
    assert 'private' not in str(error.value)
    assert error.value.__suppress_context__ is True
    assert error.value.__context__ is None


def test_real_child_echo_and_no_input_mutation():
    value = bundle()
    raw = json.dumps(value).encode()
    assert run_child('import sys; sys.stdout.buffer.write(sys.stdin.buffer.read())', raw) == value


def test_public_boundary_validates_bundle_builds_constant_command_and_scrubs_env(monkeypatch):
    value = bundle()
    original = deepcopy(value)
    for name in ('DATABASE_URL', 'JWT_SECRET', 'AWS_ACCESS_KEY_ID', 'HOME', 'PYTHONPATH',
                 'OPENAI_API_KEY', 'HTTPS_PROXY', 'LD_PRELOAD', 'OPENROUTER_API_KEY'):
        monkeypatch.setenv(name, 'private-do-not-inherit')
    captured = {}
    real_transport = process._bounded_process

    def capture(argv, env, input_bytes):
        captured.update(argv=argv, env=env, raw=input_bytes)
        # Fake the runtime import, not the real transport or constant bootstrap.
        code = (
            'import json,os,sys,types; '
            'package=types.ModuleType("agent_runtime"); package.__path__=[]; '
            'module=types.ModuleType("agent_runtime.research"); '
            'module.main=lambda: (sys.stdin.buffer.read(), '
            'print(json.dumps(dict(os.environ))),0)[-1]; '
            'sys.modules.update({"agent_runtime":package,"agent_runtime.research":module}); '
            f'exec({process._BOOTSTRAP!r})'
        )
        return real_transport(child(code) + argv[7:], env, input_bytes)

    monkeypatch.setattr(process, '_bounded_process', capture)
    result = process.run_research_process(
        value, python_executable=sys.executable, api_key='synthetic-key',
        primary_model='provider/primary', fallback_models=['provider/backup'],
    )
    expected = {
        'OPENROUTER_API_KEY': 'synthetic-key', 'OPENROUTER_PRIMARY_MODEL': 'provider/primary',
        'OPENROUTER_FALLBACK_MODELS': 'provider/backup', 'AGENT_RESEARCH_ENABLED': '1',
        'ENVIRONMENT': 'development', 'OPENAI_AGENTS_DISABLE_TRACING': '1',
    }
    assert captured['env'] == expected
    assert result == expected
    assert captured['argv'][:6] == [sys.executable, '-I', '-B', '-X', 'utf8', '-c']
    assert captured['argv'][6] == process._BOOTSTRAP
    assert captured['argv'][7:] == [str(Path(process.__file__).resolve().parents[2])]
    assert '--execute' in process._BOOTSTRAP
    assert 'agent_runtime.research' in process._BOOTSTRAP
    assert b'synthetic-key' not in captured['raw']
    assert json.loads(captured['raw']) == value
    assert len(captured['raw']) <= 20000
    assert value == original


def test_bootstrap_imports_only_trusted_root_and_calls_execute(monkeypatch):
    # Exercise the constant bootstrap without importing the SDK or making a provider call.
    code = (
        'import json,sys,types; '
        'package=types.ModuleType("agent_runtime"); package.__path__=[]; '
        'module=types.ModuleType("agent_runtime.research"); '
        'module.main=lambda: (print(json.dumps({"argv":sys.argv,"root":sys.path[0]})) or 0); '
        'sys.modules.update({"agent_runtime":package,"agent_runtime.research":module}); '
        f'exec({process._BOOTSTRAP!r})'
    )
    argv = child(code) + ['/synthetic/repository']
    result = process._bounded_process(argv, {}, b'')
    assert result['argv'][1:] == ['--execute']
    assert result['root'] == '/synthetic/repository'


@pytest.mark.parametrize('invalid', [None, {}, [], {'private': 'private-input'},
                                          bundle() | {'extra': 'private'}])
def test_invalid_bundle_never_executes(monkeypatch, invalid):
    def forbidden(*_args, **_kwargs):
        pytest.fail('Invalid input must not start a process')

    monkeypatch.setattr(process.subprocess, 'Popen', forbidden)
    assert_error('invalid_bundle', lambda: process.run_research_process(
        invalid, python_executable=sys.executable, api_key='synthetic',
        primary_model='provider/primary', fallback_models=[]))


def test_exact_serialized_byte_bound_is_checked_before_process(monkeypatch):
    value = bundle()
    value['evidence'] = [{'id': 'a', 'text': '\u00e9' * 4000}]

    def forbidden(*_args, **_kwargs):
        pytest.fail('Oversize bytes must not start a process')

    monkeypatch.setattr(process.subprocess, 'Popen', forbidden)
    assert_error('invalid_bundle', lambda: process.run_research_process(
        value, python_executable=sys.executable, api_key='synthetic',
        primary_model='provider/primary', fallback_models=[]))


def test_exact_20000_serialized_bytes_allowed_and_next_byte_refused(monkeypatch):
    value = bundle()
    value['evidence'] = [{'id': 'a', 'text': 'a' * 10000}, {'id': 'b', 'text': ''}]
    remaining = 20000 - len(json.dumps(value, ensure_ascii=True, allow_nan=False).encode('utf-8'))
    assert 1 <= remaining <= 10000
    value['evidence'][1]['text'] = 'b' * remaining
    seen = []

    def capture(_argv, _env, raw):
        seen.append(raw)
        return {}

    monkeypatch.setattr(process, '_bounded_process', capture)
    config = dict(python_executable=sys.executable, api_key='synthetic',
                  primary_model='provider/primary', fallback_models=[])
    assert process.run_research_process(value, **config) == {}
    assert len(seen[0]) == 20000
    value['evidence'][1]['text'] += 'b'
    assert_error('invalid_bundle', lambda: process.run_research_process(value, **config))
    assert len(seen) == 1


@pytest.mark.parametrize('changes', [
    {'python_executable': 'python'}, {'python_executable': '/does/not/exist'},
    {'python_executable': '/'}, {'python_executable': True},
    {'python_executable': '/private\x00path'},
    {'api_key': ''}, {'api_key': None}, {'api_key': 'private\nkey'},
    {'api_key': 'x' * 4097},
    {'primary_model': ''}, {'primary_model': ['private']},
    {'primary_model': 'provider/private,other'},
    {'fallback_models': 'private'}, {'fallback_models': [True]},
    {'fallback_models': ['private\nmodel']},
    {'fallback_models': ['provider/backup'] * 17},
])
def test_invalid_server_configuration_never_executes(monkeypatch, changes):
    def forbidden(*_args, **_kwargs):
        pytest.fail('Invalid configuration must not start a process')

    monkeypatch.setattr(process.subprocess, 'Popen', forbidden)
    config = dict(python_executable=sys.executable, api_key='synthetic',
                  primary_model='provider/primary', fallback_models=[])
    assert_error('invalid_configuration', lambda: process.run_research_process(bundle(), **(config | changes)))


def test_non_executable_file_is_rejected_without_launch(tmp_path, monkeypatch):
    path = tmp_path / 'not-executable'
    path.write_text('not code')
    path.chmod(0o600)
    monkeypatch.setattr(process.subprocess, 'Popen', lambda *_a, **_k: pytest.fail('Must not launch'))
    assert_error('invalid_configuration', lambda: process.run_research_process(
        bundle(), python_executable=str(path), api_key='synthetic',
        primary_model='provider/primary', fallback_models=[]))


def test_concurrent_pipe_progress_with_large_input_and_output():
    value = {'value': 'x' * 500000}
    raw = json.dumps(value).encode()
    code = ('import sys; sys.stdout.buffer.write(b" "*100000); sys.stdout.buffer.flush(); '
            'data=sys.stdin.buffer.read(); sys.stdout.buffer.write(data)')
    assert run_child(code, raw, max_output_bytes=len(raw) + 100000, timeout_seconds=5) == value


def test_large_stderr_is_discarded_not_captured():
    code = ('import sys; sys.stderr.write("private"*100000); '
            'sys.stdin.buffer.read(); print("{}")')
    assert run_child(code) == {}


@pytest.mark.parametrize('payload', [b'\xff', b'{', b'[]', b'null', b'NaN',
                                     b'{"x":NaN}', b'{"x":1e999}',
                                     b'{"x":1,"x":2}', b'{} trailing'])
def test_malformed_utf8_json_or_non_object_is_rejected(payload):
    code = f'import sys; sys.stdin.buffer.read(); sys.stdout.buffer.write({payload!r})'
    assert_error('invalid_output', lambda: run_child(code))


def test_nonzero_output_and_stderr_are_not_exposed():
    code = ('import sys; sys.stdin.buffer.read(); print("private output"); '
            'sys.stderr.write("private error"); sys.exit(7)')
    assert_error('process_failed', lambda: run_child(code))


def test_output_cap_before_accumulation_and_exact_boundary():
    raw = b'{"x":"' + b'a' * 1000 + b'"}'
    code = f'import sys; sys.stdin.buffer.read(); sys.stdout.buffer.write({raw!r})'
    assert run_child(code, max_output_bytes=len(raw)) == {'x': 'a' * 1000}
    assert_error('process_output_limit', lambda: run_child(code, max_output_bytes=len(raw) - 1))


def test_timeout_covers_input_pipe_when_child_never_reads():
    assert_error('process_timeout', lambda: run_child(
        'import time; time.sleep(20)', b'x' * 500000, timeout_seconds=0.15))


def test_timeout_covers_wait_after_stdout_eof():
    code = 'import os,sys,time; sys.stdin.buffer.read(); os.close(1); time.sleep(20)'
    started = time.monotonic()
    assert_error('process_timeout', lambda: run_child(code, timeout_seconds=0.15))
    assert time.monotonic() - started < 3


def test_real_popen_uses_owned_session_and_failure_reaps_leader(monkeypatch):
    original = subprocess.Popen
    children = []

    def capture(*args, **kwargs):
        assert kwargs['start_new_session'] is True
        assert kwargs['shell'] is False
        assert kwargs['stderr'] == subprocess.DEVNULL
        assert kwargs['env'] == {}
        child_process = original(*args, **kwargs)
        children.append(child_process)
        return child_process

    monkeypatch.setattr(process.subprocess, 'Popen', capture)
    assert_error('process_timeout', lambda: run_child('import time; time.sleep(20)', timeout_seconds=0.15))
    assert len(children) == 1
    assert children[0].returncode == -signal.SIGKILL
    assert children[0].stdin.closed and children[0].stdout.closed
    with pytest.raises(ChildProcessError):
        os.waitpid(children[0].pid, os.WNOHANG)


def test_group_cleanup_kills_descendant_holding_stdout_after_leader_exit(monkeypatch, tmp_path):
    original = subprocess.Popen
    group_kills = []
    reads = []
    real_killpg = os.killpg

    def capture(*args, **kwargs):
        child_process = original(*args, **kwargs)
        reads.append(os.dup(child_process.stdout.fileno()))
        return child_process

    def kill_group(pid, sig):
        group_kills.append((pid, sig))
        return real_killpg(pid, sig)

    monkeypatch.setattr(process.subprocess, 'Popen', capture)
    monkeypatch.setattr(process.os, 'killpg', kill_group)
    marker = tmp_path / 'synthetic-descendant-pid'
    code = (
        'import os,sys,time\n'
        'from pathlib import Path\n'
        'sys.stdin.buffer.read()\n'
        'pid=os.fork()\n'
        'if pid == 0:\n'
        '    time.sleep(20)\n'
        'else:\n'
        f'    Path({str(marker)!r}).write_text(str(pid))\n'
        '    sys.stdout.write("{}")\n'
        'sys.stdout.flush()\n'
        'os._exit(0)\n'
    )
    try:
        assert_error('process_timeout', lambda: run_child(code, timeout_seconds=0.5))
        assert int(marker.read_text()) > 0
        assert group_kills and all(sig == signal.SIGKILL for _pid, sig in group_kills)
        os.set_blocking(reads[0], False)
        deadline = time.monotonic() + 2
        while True:
            try:
                assert os.read(reads[0], 1) == b''
                break
            except BlockingIOError:
                assert time.monotonic() < deadline, 'Descendant retained stdout after group cleanup'
                time.sleep(0.01)
    finally:
        for descriptor in reads:
            os.close(descriptor)


def test_success_also_kills_descendant_that_closed_stdout(monkeypatch, tmp_path):
    original = subprocess.Popen
    children = []
    fifo = tmp_path / 'synthetic-descendant-liveness'
    os.mkfifo(fifo)
    reader = os.open(fifo, os.O_RDONLY | os.O_NONBLOCK)

    def capture(*args, **kwargs):
        child_process = original(*args, **kwargs)
        children.append(child_process)
        return child_process

    monkeypatch.setattr(process.subprocess, 'Popen', capture)
    code = (
        'import os,sys,time\n'
        'sys.stdin.buffer.read()\n'
        'ready_reader,ready_writer=os.pipe()\n'
        'pid=os.fork()\n'
        'if pid == 0:\n'
        '    os.close(ready_reader)\n'
        f'    alive=os.open({str(fifo)!r}, os.O_WRONLY)\n'
        '    os.write(alive,b"R")\n'
        '    os.close(1)\n'
        '    os.write(ready_writer,b"R")\n'
        '    os.close(ready_writer)\n'
        '    time.sleep(20)\n'
        '    os._exit(0)\n'
        'os.close(ready_writer)\n'
        'assert os.read(ready_reader,1) == b"R"\n'
        'os.close(ready_reader)\n'
        'print("{}",flush=True)\n'
    )
    try:
        assert run_child(code, timeout_seconds=5) == {}
        assert os.read(reader, 1) == b'R', 'Descendant must start before leader succeeds'
        deadline = time.monotonic() + 1
        while True:
            try:
                assert os.read(reader, 1) == b''
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    pytest.fail('Successful process left its stdout-closed descendant alive')
                time.sleep(0.01)
        assert children[0].returncode == 0
        assert children[0].stdin.closed and children[0].stdout.closed
        with pytest.raises(ChildProcessError):
            os.waitpid(children[0].pid, os.WNOHANG)
    finally:
        # The RED run must not leak the descendant it deliberately reproduces.
        for child_process in children:
            try:
                os.killpg(child_process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            child_process.wait(timeout=2)
        os.close(reader)


def test_spawn_exception_is_sanitized(monkeypatch):
    def fail(*_args, **_kwargs):
        raise OSError('private launch error')

    monkeypatch.setattr(process.subprocess, 'Popen', fail)
    assert_error('process_start_failed', lambda: run_child('print("{}")'))


def test_malformed_output_also_cleans_owned_group(monkeypatch):
    calls = []
    original = os.killpg

    def record(pid, sig):
        calls.append((pid, sig))
        return original(pid, sig)

    monkeypatch.setattr(process.os, 'killpg', record)
    assert_error('invalid_output', lambda: run_child('import sys; sys.stdin.buffer.read(); print("private")'))
    assert calls and calls[0][1] == signal.SIGKILL


def test_public_result_does_not_validate_domain_separately_owned_by_parent(monkeypatch):
    monkeypatch.setattr(process, '_bounded_process', lambda *_a, **_k: {'arbitrary': 'object'})
    assert process.run_research_process(
        bundle(), python_executable=sys.executable, api_key='synthetic',
        primary_model='provider/primary', fallback_models=[],
    ) == {'arbitrary': 'object'}


@pytest.mark.parametrize('kwargs', [
    {'timeout_seconds': 0}, {'timeout_seconds': -1}, {'timeout_seconds': True},
    {'timeout_seconds': float('nan')}, {'timeout_seconds': float('inf')},
    {'max_output_bytes': 0}, {'max_output_bytes': True},
])
def test_bad_transport_limits_do_not_spawn(monkeypatch, kwargs):
    monkeypatch.setattr(process.subprocess, 'Popen', lambda *_a, **_k: pytest.fail('Must not launch'))
    assert_error('invalid_configuration', lambda: run_child('print("{}")', **kwargs))


def test_pipe_setup_failure_kills_and_reaps_child(monkeypatch):
    children = []
    original = subprocess.Popen

    def capture(*args, **kwargs):
        child_process = original(*args, **kwargs)
        children.append(child_process)
        return child_process

    def fail(*_args):
        raise OSError('private descriptor failure')

    monkeypatch.setattr(process.subprocess, 'Popen', capture)
    monkeypatch.setattr(process.os, 'set_blocking', fail)
    assert_error('process_io_failed', lambda: run_child('import time; time.sleep(20)'))
    assert children[0].returncode == -signal.SIGKILL
    assert children[0].stdin.closed and children[0].stdout.closed
