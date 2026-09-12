"""Opt-in real Redis checks; REDIS_SERVER_BINARY launches only a private child.

Run via scripts/verify_auth_abuse.py to clear REDIS_URL before conftest imports.
No existing Redis instance is used, and no database-wide cleanup is performed.
"""

from __future__ import annotations

import hashlib
import os
import secrets
import socket
import subprocess
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("REDIS_SERVER_BINARY", "").strip(),
    reason="Set REDIS_SERVER_BINARY to opt into disposable real Redis tests",
)


@dataclass
class _RedisProcess:
    process: subprocess.Popen
    directory: Path
    url: str = field(repr=False)
    client: object = field(repr=False)

    def stop(self):
        """Signal and reap only the subprocess this fixture created."""
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)


@contextmanager
def _private_redis():
    import redis

    binary = Path(os.environ["REDIS_SERVER_BINARY"]).expanduser()
    if not binary.is_absolute() or not binary.is_file() or not os.access(binary, os.X_OK):
        pytest.fail("REDIS_SERVER_BINARY must be an absolute executable file path")
    if os.environ.get("REDIS_URL", "").strip():
        pytest.fail("Run with REDIS_URL='' or use scripts/verify_auth_abuse.py")

    with tempfile.TemporaryDirectory(prefix="auth-abuse-redis-") as temporary:
        directory = Path(temporary).resolve()
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as reservation:
            reservation.bind(("127.0.0.1", 0))
            port = reservation.getsockname()[1]
        password = secrets.token_hex(24)
        url = f"redis://:{password}@127.0.0.1:{port}/0"
        log_path = directory / "redis.log"
        with log_path.open("wb") as log:
            process = subprocess.Popen(
                [
                    str(binary),
                    "--bind",
                    "127.0.0.1",
                    "--port",
                    str(port),
                    "--protected-mode",
                    "yes",
                    "--requirepass",
                    password,
                    "--save",
                    "",
                    "--appendonly",
                    "no",
                    "--daemonize",
                    "no",
                    "--dir",
                    str(directory),
                    "--dbfilename",
                    "unused.rdb",
                    "--pidfile",
                    str(directory / "redis.pid"),
                    "--logfile",
                    "",
                    "--databases",
                    "1",
                ],
                cwd=directory,
                env={**os.environ, "REDIS_URL": ""},
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
            )
            client = redis.Redis.from_url(
                url,
                socket_connect_timeout=0.5,
                socket_timeout=0.5,
            )
            server = _RedisProcess(process, directory, url, client)
            try:
                # Readiness from our child's log avoids contacting a different
                # service if another process wins the ephemeral-port race.
                deadline = time.monotonic() + 10
                while True:
                    output = log_path.read_text(errors="replace")
                    if process.poll() is not None:
                        pytest.fail(f"Private Redis exited during startup:\n{output}")
                    if "Ready to accept connections" in output:
                        break
                    if time.monotonic() >= deadline:
                        pytest.fail(f"Private Redis did not become ready:\n{output}")
                    time.sleep(0.02)
                info = client.info("server")
                assert info["process_id"] == process.pid
                assert int(info["redis_version"].split(".")[0]) >= 7, "Redis 7+ required"
                assert client.config_get("bind")["bind"] == "127.0.0.1"
                assert Path(client.config_get("dir")["dir"]).resolve() == directory
                assert client.config_get("save")["save"] == ""
                assert client.config_get("appendonly")["appendonly"] == "no"
                assert client.dbsize() == 0
                yield server
            finally:
                try:
                    client.close()
                    client.connection_pool.disconnect()
                finally:
                    server.stop()
                assert not list(directory.rglob("*.rdb")), "Redis wrote a snapshot"
                assert not list(directory.rglob("*.aof*")), "Redis wrote an append-only file"


@pytest.fixture
def redis_server():
    with _private_redis() as server:
        yield server


@pytest.fixture
def backend_factory(redis_server):
    instances = []

    def create(backend_type):
        instance = backend_type(redis_server.url)
        instances.append(instance)
        return instance

    yield create
    for instance in instances:
        instance._client.close()
        instance._client.connection_pool.disconnect()


@pytest.fixture
def rate_clients(backend_factory):
    from app.services.rate_limiter import RedisRateLimiter

    return backend_factory(RedisRateLimiter), backend_factory(RedisRateLimiter)


@pytest.fixture
def lockout_clients(backend_factory, monkeypatch):
    from app.services import account_lockout

    monkeypatch.setattr(account_lockout, "MAX_ATTEMPTS", 5)
    monkeypatch.setattr(account_lockout, "LOCK_WINDOW", 2)
    return (
        backend_factory(account_lockout.RedisAccountLockout),
        backend_factory(account_lockout.RedisAccountLockout),
    )


def _only_key(client):
    keys = set(client.scan_iter())
    assert len(keys) == 1, keys
    return keys.pop()


def _assert_digest_key(stored, logical):
    digest = hashlib.sha256(logical.encode("utf-8")).hexdigest().encode("ascii")
    assert stored.endswith(b":" + digest)
    assert len(stored) > len(digest) + 1
    assert logical.encode("utf-8") not in stored


def _expiry(client, key):
    expiry = client.pexpiretime(key)
    assert expiry > 0, f"Missing expiry for {key!r}: {expiry}"
    return expiry


def _await_expiry(client, key, timeout=5):
    deadline = time.monotonic() + timeout
    while client.exists(key):
        assert time.monotonic() < deadline, f"Key did not expire: {key!r}"
        time.sleep(0.02)


def _concurrent(count, operation):
    workers = min(count, 16)
    start = threading.Barrier(workers)

    def run(worker):
        start.wait(timeout=10)
        return [operation(index) for index in range(worker, count, workers)]

    with ThreadPoolExecutor(max_workers=workers) as pool:
        return [value for batch in pool.map(run, range(workers)) for value in batch]


def test_owned_server_configuration_and_cleanup():
    with _private_redis() as server:
        process = server.process
        directory = server.directory
        assert server.client.ping()
        server.client.set("fixture-only-sentinel", "discard-on-exit")
    assert process.poll() is not None
    assert not directory.exists()


def test_rate_concurrent_exact_admission_across_independent_clients(redis_server, rate_clients):
    first, second = rate_clients
    assert first._client.connection_pool is not second._client.connection_pool
    logical = "login:victim@example.test:192.0.2.4"
    limit, window = 17, 10

    def check(index):
        decision = rate_clients[index % 2].check(
            key=logical,
            limit=limit,
            window_seconds=window,
            required=True,
        )
        key = _only_key(redis_server.client)
        assert 0 < redis_server.client.pttl(key) <= window * 1000
        return decision, _expiry(redis_server.client, key)

    results = _concurrent(64, check)
    decisions = [result[0] for result in results]
    allowed = [decision for decision in decisions if decision.allowed]
    denied = [decision for decision in decisions if not decision.allowed]
    assert len(allowed) == limit
    assert len(denied) == 64 - limit
    assert sorted(decision.remaining for decision in allowed) == list(range(limit))
    assert all(decision.retry_after == 0 for decision in allowed)
    assert all(
        decision.remaining == 0 and 1 <= decision.retry_after <= window for decision in denied
    )
    assert len({result[1] for result in results}) == 1
    _assert_digest_key(_only_key(redis_server.client), logical)


def test_rate_uses_one_real_single_key_eval(redis_server, rate_clients, monkeypatch):
    first, _ = rate_clients
    commands = []
    execute = first._client.execute_command

    def record(*args, **kwargs):
        commands.append(args)
        return execute(*args, **kwargs)

    monkeypatch.setattr(first._client, "execute_command", record)
    assert first.check(key="eval-contract", limit=1, window_seconds=10, required=True).allowed
    assert len(commands) == 1
    assert commands[0][0] == "EVAL"
    assert commands[0][2] == 1
    assert commands[0][3].encode("utf-8") == _only_key(redis_server.client)
    assert redis_server.client.info("commandstats")["cmdstat_eval"]["calls"] == 1


def test_rate_window_expires_without_extension_on_blocked_hits(redis_server, rate_clients):
    first, second = rate_clients
    policy = {"key": "fixed-window", "limit": 1, "window_seconds": 2, "required": True}
    assert first.check(**policy).allowed
    key = _only_key(redis_server.client)
    deadline = _expiry(redis_server.client, key)
    for _ in range(4):
        time.sleep(0.08)
        denied = second.check(**policy)
        assert not denied.allowed and 1 <= denied.retry_after <= 2
        assert _expiry(redis_server.client, key) == deadline
    _await_expiry(redis_server.client, key)
    assert second.check(**policy).allowed
    assert not first.check(**policy).allowed
    assert _expiry(redis_server.client, key) > deadline


def test_rate_repairs_missing_ttl_without_resetting_budget(redis_server, rate_clients):
    first, second = rate_clients
    policy = {"key": "orphaned-rate", "limit": 2, "window_seconds": 2, "required": True}
    assert first.check(**policy).remaining == 1
    key = _only_key(redis_server.client)
    assert redis_server.client.persist(key)
    assert redis_server.client.pttl(key) == -1
    repaired = second.check(**policy)
    assert repaired.allowed and repaired.remaining == 0
    assert 0 < redis_server.client.pttl(key) <= 2000
    assert not first.check(**policy).allowed


def test_rate_reset_and_disabled_clear_preserve_other_keys(redis_server, rate_clients):
    first, second = rate_clients
    logical = "login:alice@example.test"
    redis_server.client.set(logical, "raw-key-sentinel")
    redis_server.client.set("unrelated:sentinel", "keep")
    for key in (logical, "login:bob@example.test"):
        assert first.check(key=key, limit=1, window_seconds=10, required=True).allowed
    before = {key: redis_server.client.dump(key) for key in redis_server.client.scan_iter()}
    with pytest.raises(RuntimeError):
        first.clear()
    assert {key: redis_server.client.dump(key) for key in redis_server.client.scan_iter()} == before
    second.reset(logical, required=True)
    second.reset(logical, required=True)
    assert redis_server.client.get(logical) == b"raw-key-sentinel"
    assert redis_server.client.get("unrelated:sentinel") == b"keep"
    assert not first.check(
        key="login:bob@example.test", limit=1, window_seconds=10, required=True
    ).allowed
    assert first.check(key=logical, limit=1, window_seconds=10, required=True).allowed


def test_rate_wrong_type_fails_closed_when_required(redis_server, rate_clients):
    from app.services.rate_limiter import RateLimitUnavailable

    first, second = rate_clients
    policy = {"key": "corrupt-rate", "limit": 1, "window_seconds": 10}
    assert first.check(**policy, required=True).allowed
    key = _only_key(redis_server.client)
    redis_server.client.delete(key)
    redis_server.client.hset(key, "unexpected", "type")
    with pytest.raises(RateLimitUnavailable):
        second.check(**policy, required=True)
    assert first.check(**policy).allowed


def test_rate_errors_after_owned_server_stop(redis_server, rate_clients):
    from app.services.rate_limiter import RateLimitUnavailable

    first, second = rate_clients
    policy = {"key": "stopped-server", "limit": 1, "window_seconds": 10}
    assert first.check(**policy, required=True).allowed
    assert not second.check(**policy, required=True).allowed
    redis_server.stop()
    assert redis_server.process.poll() is not None
    for limiter in rate_clients:
        with pytest.raises(RateLimitUnavailable):
            limiter.check(**policy, required=True)
        with pytest.raises(RateLimitUnavailable):
            limiter.reset(policy["key"], required=True)
        assert limiter.check(**policy).allowed
        assert limiter.reset(policy["key"]) is None


def test_lockout_shared_threshold_normalizes_email(redis_server, lockout_clients):
    first, second = lockout_clients
    assert first._client.connection_pool is not second._client.connection_pool
    for index in range(5):
        assert not second.is_locked("victim@example.test")[0]
        assert lockout_clients[index % 2].record_failure(" Victim@Example.test ") == index + 1
    for lockout in lockout_clients:
        locked, retry = lockout.is_locked("VICTIM@example.test")
        assert locked and 1 <= retry <= 2
    _assert_digest_key(_only_key(redis_server.client), "victim@example.test")


def test_lockout_concurrent_failures_are_not_lost(redis_server, lockout_clients, monkeypatch):
    from app.services import account_lockout

    monkeypatch.setattr(account_lockout, "MAX_ATTEMPTS", 65)
    monkeypatch.setattr(account_lockout, "LOCK_WINDOW", 10)
    counts = _concurrent(
        64,
        lambda index: lockout_clients[index % 2].record_failure("parallel@example.test"),
    )
    assert sorted(counts) == list(range(1, 65))
    assert not lockout_clients[0].is_locked("parallel@example.test")[0]
    assert lockout_clients[1].record_failure("parallel@example.test") == 65
    assert lockout_clients[0].is_locked("parallel@example.test")[0]
    assert 0 < redis_server.client.pttl(_only_key(redis_server.client)) <= 10000


def test_lockout_blocked_hits_do_not_extend_ttl_and_expiry_resets(redis_server, lockout_clients):
    first, second = lockout_clients
    email = "locked@example.test"
    for _ in range(5):
        first.record_failure(email)
    key = _only_key(redis_server.client)
    deadline = _expiry(redis_server.client, key)
    for _ in range(4):
        time.sleep(0.08)
        locked, retry = second.is_locked(email)
        assert locked and 1 <= retry <= 2
        assert second.record_failure(email) == 5
        assert _expiry(redis_server.client, key) == deadline
    _await_expiry(redis_server.client, key)
    assert first.is_locked(email) == (False, 0)
    assert second.record_failure(email) == 1
    assert first.is_locked(email) == (False, 0)


def test_lockout_observation_window_expires_below_threshold(redis_server, lockout_clients):
    first, second = lockout_clients
    email = "observation@example.test"
    assert first.record_failure(email) == 1
    key = _only_key(redis_server.client)
    deadline = _expiry(redis_server.client, key)
    time.sleep(0.08)
    assert second.record_failure(email) == 2
    assert second.is_locked(email) == (False, 0)
    assert _expiry(redis_server.client, key) == deadline
    _await_expiry(redis_server.client, key)
    assert second.record_failure(email) == 1
    assert first.is_locked(email) == (False, 0)


def test_lockout_threshold_starts_a_fresh_lock_window(redis_server, lockout_clients):
    first, second = lockout_clients
    email = "threshold@example.test"
    assert first.record_failure(email) == 1
    key = _only_key(redis_server.client)
    observation_deadline = _expiry(redis_server.client, key)
    time.sleep(0.08)
    for expected in range(2, 5):
        assert second.record_failure(email) == expected
        assert _expiry(redis_server.client, key) == observation_deadline
    assert first.record_failure(email) == 5
    assert second.is_locked(email)[0]
    assert _expiry(redis_server.client, key) > observation_deadline


def test_lockout_reset_isolated_from_accounts_and_rate_namespace(
    redis_server, lockout_clients, rate_clients
):
    first, second = lockout_clients
    alice, bob = "alice@example.test", "bob@example.test"
    for email in (alice, bob):
        for _ in range(5):
            first.record_failure(email)
    redis_server.client.set("unrelated:sentinel", "keep")
    assert rate_clients[0].check(key=alice, limit=1, window_seconds=10, required=True).allowed
    before = {key: redis_server.client.dump(key) for key in redis_server.client.scan_iter()}
    with pytest.raises(RuntimeError):
        first.clear()
    assert {key: redis_server.client.dump(key) for key in redis_server.client.scan_iter()} == before
    second.reset(" ALICE@example.test ")
    second.reset(alice)
    assert first.is_locked(alice) == (False, 0)
    assert first.record_failure(alice) == 1
    assert second.is_locked(bob)[0]
    assert redis_server.client.get("unrelated:sentinel") == b"keep"
    assert not rate_clients[1].check(key=alice, limit=1, window_seconds=10, required=True).allowed
    rate_clients[1].reset(alice, required=True)
    assert second.record_failure(alice) == 2
    assert first.is_locked(bob)[0]


@pytest.mark.parametrize("locked", [False, True])
@pytest.mark.parametrize("operation", ["is_locked", "record_failure"])
def test_lockout_repairs_missing_ttl(redis_server, lockout_clients, locked, operation):
    first, second = lockout_clients
    email = "orphaned-lockout@example.test"
    count = 5 if locked else 1
    for _ in range(count):
        first.record_failure(email)
    key = _only_key(redis_server.client)
    assert redis_server.client.persist(key)
    assert redis_server.client.pttl(key) == -1
    result = getattr(second, operation)(email)
    if operation == "is_locked":
        assert result[0] is locked
        assert (1 <= result[1] <= 2) if locked else result[1] == 0
    else:
        assert result == min(5, count + 1)
    assert 0 < redis_server.client.pttl(key) <= 2000
    assert first.is_locked(email)[0] is locked


@pytest.mark.parametrize("operation", ["is_locked", "record_failure"])
def test_lockout_wrong_type_always_fails_closed(redis_server, lockout_clients, operation):
    from app.services.rate_limiter import RateLimitUnavailable

    first, second = lockout_clients
    email = "corrupt@example.test"
    assert first.record_failure(email) == 1
    key = _only_key(redis_server.client)
    redis_server.client.delete(key)
    redis_server.client.hset(key, "unexpected", "type")
    with pytest.raises(RateLimitUnavailable):
        getattr(second, operation)(email)


@pytest.mark.parametrize("operation", ["is_locked", "record_failure", "reset"])
def test_lockout_errors_after_owned_server_stop(redis_server, lockout_clients, operation):
    from app.services.rate_limiter import RateLimitUnavailable

    first, second = lockout_clients
    email = "stopped@example.test"
    assert first.record_failure(email) == 1
    assert second.record_failure(email) == 2
    redis_server.stop()
    assert redis_server.process.poll() is not None
    for lockout in lockout_clients:
        with pytest.raises(RateLimitUnavailable):
            getattr(lockout, operation)(email)
