"""Use only the ASGI server's validated peer, never raw forwarding headers."""
from __future__ import annotations

from ipaddress import ip_address

from starlette.requests import Request


def client_address(request: Request) -> str:
    # Configure proxy trust at the server boundary. Parsing X-Forwarded-For
    # again here would let an untrusted caller choose their own throttle key.
    host = request.client.host if request.client else "unknown"
    try:
        return str(ip_address(host))
    except ValueError:
        return host
