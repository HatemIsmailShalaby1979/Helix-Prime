"""Runtime configuration for the Helix Codex App.

Every setting is read from the environment with a HELIX_APP_ prefix. App
secrets follow the parent rule: no default for a secret, and the app refuses
to boot on an unsafe bind address. The host must be a loopback address unless
the operator explicitly accepts the risk.
"""
from __future__ import annotations

import ipaddress
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="HELIX_APP_",
        env_file=".env",
        extra="ignore",
    )

    db_path: str = "helix_codex_app/app.db"
    memory_root: str = "helix_codex_app/memory_stores"
    host: str = "127.0.0.1"
    port: int = 8100
    session_idle_minutes: int = 720
    session_absolute_days: int = 30
    cors_origins: list[str] = Field(default_factory=list)

    def require_safe_defaults(self) -> None:
        if not _is_loopback(self.host):
            raise RuntimeError(
                f"HELIX_APP_HOST={self.host} is not a loopback address. "
                "Refusing to start; the app is a self-hosted box, not a public service."
            )


def _is_loopback(host: str) -> bool:
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return host.lower() == "localhost"


@lru_cache(maxsize=1)
def get_app_settings() -> AppSettings:
    """Process-wide app settings. Cached so config is read once, at first use."""
    return AppSettings()
