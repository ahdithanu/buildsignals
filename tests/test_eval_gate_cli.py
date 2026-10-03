"""Network-free gate CLI checks, including urllib's actual redirect machinery."""
import json
import socket
import ssl
from email.message import Message
from io import BytesIO
from types import SimpleNamespace
from urllib.error import HTTPError, URLError
from urllib.request import HTTPHandler, HTTPSHandler, build_opener
from urllib.response import addinfourl

import pytest

from scripts import check_eval_gate as cli

RUN_ID = "run-123"
TOKEN = "test-secret-never-print"
PASSED = {"id": RUN_ID, "status": "completed", "gate_passed": True}


@pytest.fixture(autouse=True)
def environment_and_no_network(monkeypatch):
    monkeypatch.setenv("EVAL_BASE_URL", "https://eval.example")
    monkeypatch.setenv("EVAL_ACCESS_TOKEN", TOKEN)

    def forbidden_network(*args, **kwargs):
        pytest.fail("Gate CLI tests must not use the network")

    monkeypatch.setattr(socket, "create_connection", forbidden_network)
    monkeypatch.setattr(socket.socket, "connect", forbidden_network)


@pytest.fixture
def transport(monkeypatch):
    class FakeTransport(HTTPHandler, HTTPSHandler):
        def __init__(self):
            HTTPHandler.__init__(self)
            self.requests = []
            self.status = 200
            self.body = json.dumps(PASSED).encode()
            self.location = None
            self.error = None

        def http_open(self, request):
            self.requests.append(request)
            if self.error:
                raise self.error
            headers = Message()
            headers["Content-Type"] = "application/json"
            if self.location:
                headers["Location"] = self.location
            response = addinfourl(BytesIO(self.body), headers, request.full_url, self.status)
            response.msg = "test response"
            return response

        https_open = http_open

    fake = FakeTransport()
    monkeypatch.setattr(cli, "build_opener", lambda *handlers: build_opener(*handlers, fake))
    return fake


def test_success_request_contract_and_no_secrets(transport, capsys):
    assert cli.main([RUN_ID]) == 0
    assert len(transport.requests) == 1
    request = transport.requests[0]
    assert request.full_url == f"https://eval.example/v1/evals/runs/{RUN_ID}/gate"
    assert request.get_method() == "GET"
    assert request.data is None
    assert request.get_header("Accept") == "application/json"
    assert request.get_header("Authorization") == f"Bearer {TOKEN}"
    assert "Authorization" not in request.headers
    assert request.timeout == cli.TIMEOUT_SECONDS
    captured = capsys.readouterr()
    assert captured.out == "Evaluation gate passed.\n"
    assert captured.err == ""
    assert TOKEN not in captured.out


@pytest.mark.parametrize("base", [
    "https://eval.example/", "https://eval.example/prefix", "https://eval.example:8443",
    "http://localhost:8000", "http://LOCALHOST:8000", "http://127.0.0.1:8000",
    "http://127.0.0.2:8000", "http://[::1]:8000",
])
def test_secure_remote_or_literal_loopback_urls(base, monkeypatch, transport):
    monkeypatch.setenv("EVAL_BASE_URL", base)
    assert cli.main([RUN_ID]) == 0
    assert transport.requests[0].full_url == f"{base.rstrip('/')}/v1/evals/runs/{RUN_ID}/gate"


@pytest.mark.parametrize("base", [
    "", "eval.example", "ftp://eval.example", "http://eval.example",
    "http://localhost.evil.example", "http://127.0.0.1.evil.example", "http://192.168.1.1",
    "http://0.0.0.0", "http://[::]", "http://2130706433", "http://127.1",
    "http://localhost@evil.example", "https://user:secret@eval.example",
    "https://eval.example?token=secret", "https://eval.example/#secret",
    "https://eval.example?", "https://eval.example#", "https://eval.example:bad",
    "https://eval.example:65536", "https://eval.example:0", "https://[broken",
    "https://", " https://eval.example", "https://eval.example\n",
    "https://eval.\texample", "https://eval.example/\x00", "https://eval.example/\x7f",
    "https://local%68ost", "https://eval.example\\@evil.example",
])
def test_invalid_or_insecure_configuration_never_sends_token(base, monkeypatch, transport, capsys):
    # Real OS environment variables reject NUL before the CLI can inspect it.
    monkeypatch.setattr(cli, "os", SimpleNamespace(environ={
        "EVAL_BASE_URL": base, "EVAL_ACCESS_TOKEN": TOKEN,
    }))
    assert cli.main([RUN_ID]) == 2
    assert transport.requests == []
    captured = capsys.readouterr()
    assert captured.out == ""
    assert TOKEN not in captured.err
    assert "secret" not in captured.err


@pytest.mark.parametrize("variable", ["EVAL_BASE_URL", "EVAL_ACCESS_TOKEN"])
def test_missing_environment_fails_closed(variable, monkeypatch, transport):
    monkeypatch.delenv(variable)
    assert cli.main([RUN_ID]) == 2
    assert transport.requests == []


@pytest.mark.parametrize("token", [
    "", " ", "secret\r\nInjected: yes", "secret with spaces", "secret\x00", "secret\x7f",
])
def test_invalid_token_is_not_sent_or_printed(token, monkeypatch, transport, capsys):
    monkeypatch.setattr(cli, "os", SimpleNamespace(environ={
        "EVAL_BASE_URL": "https://eval.example", "EVAL_ACCESS_TOKEN": token,
    }))
    assert cli.main([RUN_ID]) == 2
    assert transport.requests == []
    assert "secret" not in capsys.readouterr().err


def test_url_validator_rejects_nul_before_url_parsing():
    with pytest.raises(ValueError):
        cli._gate_url("https://eval.example/\x00", RUN_ID)


@pytest.mark.parametrize("run_id", ["", "../other", "a/b", "a?token=x", "a#frag", ".", "a\n", "a" * 129])
def test_run_id_cannot_change_request_path(run_id, transport):
    assert cli.main([run_id]) == 2
    assert transport.requests == []


@pytest.mark.parametrize("argv", [[], [RUN_ID, "--token", TOKEN], [RUN_ID, TOKEN]])
def test_usage_errors_never_echo_arguments(argv, capsys, transport):
    with pytest.raises(SystemExit) as error:
        cli.main(argv)
    assert error.value.code == 2
    captured = capsys.readouterr()
    assert TOKEN not in captured.err + captured.out
    assert transport.requests == []


@pytest.mark.parametrize("status", [201, 202, 204, 400, 401, 403, 404, 409, 429, 500, 503])
def test_every_non_200_status_fails_even_with_passing_body(status, transport, capsys):
    transport.status = status
    assert cli.main([RUN_ID]) == 1
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize("status", [301, 302, 303, 307, 308])
@pytest.mark.parametrize("destination", [
    "https://other.example/stolen", "http://other.example/stolen",
    "https://eval.example/new-gate", "/new-gate",
])
def test_redirects_are_never_followed(status, destination, transport, capsys):
    transport.status = status
    transport.location = destination
    transport.body = TOKEN.encode()
    assert cli.main([RUN_ID]) == 1
    assert len(transport.requests) == 1
    captured = capsys.readouterr()
    assert TOKEN not in captured.err + captured.out
    assert destination not in captured.err + captured.out


@pytest.mark.parametrize("payload", [
    {}, [], None, True, {**PASSED, "gate_passed": False}, {**PASSED, "gate_passed": "true"},
    {**PASSED, "gate_passed": 1}, {**PASSED, "status": "running"},
    {**PASSED, "status": "failed"}, {**PASSED, "id": "another-run"},
    {"status": "completed", "gate_passed": True}, {"id": RUN_ID, "gate_passed": True},
    {"id": RUN_ID, "status": "completed"},
])
def test_200_requires_explicit_pass_completed_status_and_matching_id(payload, transport):
    transport.body = json.dumps(payload).encode()
    assert cli.main([RUN_ID]) == 1


@pytest.mark.parametrize("body", [
    b"", b"not JSON", b"<html>Login</html>", b"\xff", b"[", b"null trailing", TOKEN.encode(),
])
def test_malformed_response_fails_closed(body, transport, capsys):
    transport.body = body
    assert cli.main([RUN_ID]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert TOKEN not in captured.err


def test_response_size_is_bounded(transport):
    transport.body = json.dumps(PASSED).encode() + b" " * cli.MAX_RESPONSE_BYTES
    assert cli.main([RUN_ID]) == 1


@pytest.mark.parametrize("error", [
    URLError(TOKEN), TimeoutError(TOKEN), ssl.SSLCertVerificationError(TOKEN),
    ConnectionError(TOKEN), RuntimeError(TOKEN),
    HTTPError(f"https://eval.example/{TOKEN}", 409, TOKEN, {}, BytesIO(TOKEN.encode())),
])
def test_transport_errors_fail_closed_without_sensitive_details(error, transport, capsys):
    transport.error = error
    assert cli.main([RUN_ID]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "Evaluation gate rejected or unavailable.\n"
    assert TOKEN not in captured.err


def test_environment_proxy_cannot_receive_localhost_token(monkeypatch, transport):
    monkeypatch.setenv("EVAL_BASE_URL", "http://localhost:8000")
    monkeypatch.setenv("http_proxy", "http://proxy.example:8080")
    monkeypatch.setenv("https_proxy", "http://proxy.example:8080")
    monkeypatch.setenv("no_proxy", "")
    assert cli.main([RUN_ID]) == 0
    assert transport.requests[0].host == "localhost:8000"
    assert not transport.requests[0].has_proxy()
