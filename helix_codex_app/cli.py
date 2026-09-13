"""Console entry point for the Helix Codex App.

Runs the product factory on uvicorn using HELIX_APP_ settings (loopback by
default). Equivalent to uvicorn helix_codex_app.app:create_app --factory.
"""
from __future__ import annotations


def main() -> int:
    import uvicorn

    from helix_codex_app.app import create_app
    from helix_codex_app.config import get_app_settings

    settings = get_app_settings()
    uvicorn.run(
        create_app(settings),
        host=settings.host,
        port=settings.port,
        log_level="info",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
