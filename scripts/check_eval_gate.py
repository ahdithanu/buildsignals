"""Fail-closed CI gate client using only the Python standard library."""
from __future__ import annotations

import argparse
import ipaddress
import json
import os
import re
import sys
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

TIMEOUT_SECONDS = 30
MAX_RESPONSE_BYTES = 65536


class _SafeArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        # argparse normally echoes unrecognized arguments, which may be secrets.
        super().error("expected one run ID; credentials belong in environment variables")


class _NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Even same-origin redirects fail closed: never forward a bearer token.
        return None


def _gate_url(base_url: str, run_id: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}", run_id):
        raise ValueError("Invalid run ID")
    if not base_url or any(char.isspace() or ord(char) < 32 or ord(char) == 127 for char in base_url):
        raise ValueError("Invalid base URL")
    url = urlsplit(base_url)
    if (
        url.scheme not in {"http", "https"}
        or not url.hostname
        or url.username is not None
        or url.password is not None
        or "?" in base_url
        or "#" in base_url
        or "\\" in base_url
        or "%" in url.netloc
        or (url.port is not None and not 1 <= url.port <= 65535)
    ):
        raise ValueError("Invalid base URL")
    if url.scheme == "http":
        loopback = url.hostname.lower() == "localhost"
        try:
            loopback = loopback or ipaddress.ip_address(url.hostname).is_loopback
        except ValueError:
            pass
        if not loopback:
            raise ValueError("Remote HTTP is not permitted")
    return f"{base_url.rstrip('/')}/v1/evals/runs/{run_id}/gate"


def main(argv: list[str] | None = None) -> int:
    parser = _SafeArgumentParser(
        prog="check_eval_gate.py",
        description="Check a completed evaluation gate using EVAL_BASE_URL and EVAL_ACCESS_TOKEN.",
    )
    parser.add_argument("run_id", help="ID of the evaluation run to check")
    args = parser.parse_args(argv)
    try:
        url = _gate_url(os.environ.get("EVAL_BASE_URL", ""), args.run_id)
        token = os.environ.get("EVAL_ACCESS_TOKEN", "")
        if not re.fullmatch(r"[A-Za-z0-9._~+/-]+=*", token):
            raise ValueError("Invalid bearer token")
    except ValueError:
        print("Invalid gate configuration: check run ID, EVAL_BASE_URL, and EVAL_ACCESS_TOKEN.", file=sys.stderr)
        return 2

    try:
        request = Request(url, method="GET", headers={"Accept": "application/json"})
        request.add_unredirected_header("Authorization", f"Bearer {token}")
        # Direct connections avoid sending localhost HTTP tokens via an ambient
        # remote proxy. urllib's default HTTPS handler verifies TLS certificates.
        opener = build_opener(ProxyHandler({}), _NoRedirects())
        with opener.open(request, timeout=TIMEOUT_SECONDS) as response:
            if response.status != 200:
                raise ValueError("Unexpected HTTP status")
            body = response.read(MAX_RESPONSE_BYTES + 1)
        if len(body) > MAX_RESPONSE_BYTES:
            raise ValueError("Oversized gate response")
        payload = json.loads(body)
        if (
            not isinstance(payload, dict)
            or payload.get("id") != args.run_id
            or payload.get("status") != "completed"
            or payload.get("gate_passed") is not True
        ):
            raise ValueError("Gate did not pass")
    except Exception:
        # Exceptions, response bodies, URLs, and headers may contain credentials.
        # Never echo them, even for HTTP errors, TLS failures, or malformed JSON.
        print("Evaluation gate rejected or unavailable.", file=sys.stderr)
        return 1
    print("Evaluation gate passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
