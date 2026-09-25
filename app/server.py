"""API launcher with an explicit proxy boundary, shared by hosting templates."""
from __future__ import annotations

import os
from ipaddress import collapse_addresses, ip_network
from typing import Mapping

import uvicorn


def server_options(environ: Mapping[str, str] | None = None) -> dict:
    env = os.environ if environ is None else environ
    production = env.get("ENVIRONMENT", "development").strip().lower() == "production"
    raw = env.get("FORWARDED_ALLOW_IPS")
    if production and (raw is None or not raw.strip()):
        raise ValueError("Set FORWARDED_ALLOW_IPS to reviewed proxy IPs/CIDRs, or 'none' for a direct listener")
    raw = "127.0.0.1" if raw is None else raw.strip()
    peers = [] if raw.lower() == "none" else [part.strip() for part in raw.split(",")]
    networks = []
    for peer in peers:
        try:
            network = ip_network(peer)
        except ValueError:
            raise ValueError("FORWARDED_ALLOW_IPS must contain explicit IPs/CIDRs, never wildcard trust") from None
        if network.prefixlen == 0:
            raise ValueError("FORWARDED_ALLOW_IPS cannot trust the entire internet")
        networks.append(network)
    for version in (4, 6):
        if any(network.prefixlen == 0 for network in collapse_addresses(
            network for network in networks if network.version == version
        )):
            raise ValueError("FORWARDED_ALLOW_IPS cannot collectively trust an entire address family")
    port = int(env.get("PORT", "8000"))
    workers = int(env.get("WEB_CONCURRENCY", "1"))
    if not 1 <= port <= 65535 or workers < 1:
        raise ValueError("PORT and WEB_CONCURRENCY must be positive, valid server settings")
    return {
        "host": "0.0.0.0", "port": port, "workers": workers,
        "proxy_headers": bool(peers), "forwarded_allow_ips": peers,
    }


def main() -> None:
    uvicorn.run("app.main:app", **server_options())


if __name__ == "__main__":
    main()
