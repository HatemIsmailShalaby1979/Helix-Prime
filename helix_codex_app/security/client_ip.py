"""Resolve the caller's real address behind the public front door.

The app is loopback-bound, so a hosted request arrives as
Cloudflare Worker -> Quick Tunnel -> ``127.0.0.1``. At that point
``request.client.host`` is the tunnel's own local connection, identical for every
visitor, and is useless as a rate-limit key: keying on it bounds all visitors as
one caller or none of them correctly.

Measured 2026-09-27 through the real chain, with the caller's egress address known
independently (``197.132.77.25``):

===========================  ==========================================
path                         ``cf-connecting-ip`` seen by the app
===========================  ==========================================
tunnel direct                ``197.132.77.25`` — the visitor
through the Worker           ``2a06:98c0:3600::103`` — Cloudflare's egress
===========================  ==========================================

Cloudflare rewrites ``cf-connecting-ip`` on the Worker's outbound fetch, so once
the Worker is in the path that header describes Cloudflare rather than the caller.
The Worker therefore copies the visitor's address into ``x-helix-client-ip``,
which Cloudflare does not rewrite, and this module prefers it.

The header is trusted, and the reason is topological rather than cryptographic:
the app binds to loopback, the Worker is the only path in from outside, and the
Worker always sets or deletes the header rather than forwarding a caller's value.
If the app is ever exposed without the Worker in front, that trust no longer holds
and this module's ordering must be revisited.
"""
from __future__ import annotations

from ipaddress import ip_address

from fastapi import Request

WORKER_CLIENT_IP_HEADER = "x-helix-client-ip"
EDGE_CLIENT_IP_HEADER = "cf-connecting-ip"


def client_ip(request: Request) -> str | None:
    """The best available address for the caller, falling back to the peer.

    A header value is used only when it parses as an IP address, so a malformed
    or oversized value cannot become a rate-limit bucket key.
    """
    for header in (WORKER_CLIENT_IP_HEADER, EDGE_CLIENT_IP_HEADER):
        candidate = _as_ip(request.headers.get(header))
        if candidate is not None:
            return candidate
    if request.client is not None:
        return request.client.host
    return None


def _as_ip(value: str | None) -> str | None:
    if not value:
        return None
    candidate = value.strip()
    try:
        return str(ip_address(candidate))
    except ValueError:
        return None
