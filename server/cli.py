"""
Canonical console entry point for the Helix Codex OS service spine.

Runs the governed FastAPI spine — the ONE deployable artifact — using the
same settings the container profile reads. Equivalent to
`uvicorn server.app:create_app --factory` with host/port from ``HELIX_*``
settings (loopback by default).
"""

from __future__ import annotations


def main() -> int:
    import uvicorn

    from server.app import create_app
    from server.config import get_settings

    settings = get_settings()
    uvicorn.run(
        create_app(settings),
        host=settings.host,
        port=settings.port,
        log_level="info",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())