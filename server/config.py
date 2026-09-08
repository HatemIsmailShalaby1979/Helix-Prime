"""
Runtime configuration for the service spine.

Every setting is read from the environment with a ``HELIX_`` prefix, matching
the variable names ``infra/docker/`` already sets, so a containerised run needs
no new configuration surface.

Two rules shape this module:

* **No default for any secret.** A missing secret must fail at startup, not
  degrade into an unauthenticated service.
* **`production` refuses to start unsatisfied.** The release gate deliberately
  fails closed on production; the service must not quietly contradict it.
"""
from __future__ import annotations

import os
from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

Profile = Literal["local", "pilot", "production"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="HELIX_",
        env_file=".env",
        extra="ignore",
    )

    #: Deployment profile. ``production`` enforces the external gates on boot.
    profile: Profile = "local"

    #: SQLite paths. Both live under /data in the Compose profile.
    db_path: str = "control_plane/workflow.db"
    audit_db_path: str = "security/audit.db"
    log_path: str = "observability/logs.jsonl"

    #: Sample data is OFF unless explicitly enabled. Sample payloads addressed to
    #: a live run are refused at the engine boundary; this only controls whether
    #: the service starts in a mode where sample data is *offered*.
    sample_data_mode: bool = False

    #: Ollama endpoint. Optional: the service must boot without a model runtime
    #: and fail the recommendation path closed, never fabricate output.
    ollama_host: str = "http://localhost:11434"

    #: Bind address for uvicorn.
    host: str = "0.0.0.0"  # noqa: S104 - container default, overridable
    port: int = 8000

    #: CORS origins. Empty by default: this is a self-hosted box, not a SaaS.
    cors_origins: list[str] = Field(default_factory=list)

    @property
    def is_production(self) -> bool:
        return self.profile == "production"

    def require_headless_safe(self) -> None:
        """
        Fail fast when the profile cannot be honoured.

        ``production`` requires the external gates the release gate checks
        (signed evidence, certified isolation, external observer audit). Those
        are not satisfiable from configuration alone, so a production profile
        started without them is a misconfiguration, not a degraded mode.
        """
        if not self.is_production:
            return
        missing = [
            name
            for name in ("HELIX_EVIDENCE_SIGNING_KEY", "HELIX_ISOLATION_CERT", "HELIX_OBSERVER_AUDIT")
            if not os.environ.get(name)
        ]
        if missing:
            raise RuntimeError(
                "HELIX_PROFILE=production requires the external gate inputs "
                f"{missing}. Refusing to start — the release gate fails closed on "
                "these by design; do not 'fix' it by relaxing this check."
            )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Process-wide settings. Cached so config is read once, at first use."""
    return Settings()
