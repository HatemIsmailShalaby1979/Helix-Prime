"""Configuration for the cloud-ready, local-first boundary (Prompt 9).

The configuration fails safe: missing cloud services fall back to local
execution; a demo profile forbids live credentials and non-synthetic data.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .errors import SafeFailure

# Local mode allows every operation; demo mode restricts to a known set.
DEFAULT_ALLOWED = ("*",)
DEMO_ALLOWED = (
    "status", "read_synthetic", "put_synthetic", "get_synthetic",
    "reset", "shutdown", "complete_model", "publish_event",
    "record_metric", "schedule_job", "authenticate", "authorize",
)


@dataclass
class UsageLimits:
    max_requests: int = 1000
    max_records: int = 10000
    budget_usd: float = 0.50


@dataclass
class CloudConfig:
    mode: str = "local"                       # "local" | "cloud_demo"
    synthetic_data_only: bool = True
    restricted_api: bool = True
    cloud_services: dict = field(default_factory=dict)   # service -> adapter id ("local" only)
    credentials: dict = field(default_factory=dict)      # must be empty for demo
    usage_limits: UsageLimits = field(default_factory=UsageLimits)
    allowed_operations: tuple = field(default_factory=lambda: DEFAULT_ALLOWED)

    @classmethod
    def from_dict(cls, d: dict) -> "CloudConfig":
        d = dict(d or {})
        mode = d.get("mode", "local")
        ul = UsageLimits(**d.get("usage_limits", {}))
        if "allowed_operations" in d:
            allowed = tuple(d["allowed_operations"])
        elif mode == "cloud_demo":
            allowed = DEMO_ALLOWED
        else:
            allowed = DEFAULT_ALLOWED
        return cls(
            mode=mode,
            synthetic_data_only=d.get("synthetic_data_only", True),
            restricted_api=d.get("restricted_api", mode == "cloud_demo"),
            cloud_services=dict(d.get("cloud_services", {})),
            credentials=dict(d.get("credentials", {})),
            usage_limits=ul,
            allowed_operations=allowed,
        )

    def resolve(self) -> "CloudConfig":
        """Validate; raise SafeFailure on any unsafe condition."""
        for svc, aid in self.cloud_services.items():
            if aid != "local":
                raise SafeFailure(
                    f"cloud service {svc}={aid!r} is not available; "
                    f"this build is local-first"
                )
        if not self.synthetic_data_only:
            raise SafeFailure(
                "non-synthetic data mode requires an explicit production config; "
                "not allowed in this local-first build"
            )
        if self.mode == "cloud_demo" and self.credentials:
            raise SafeFailure(
                "live credentials are not permitted in the cloud_demo profile"
            )
        return self


def demo_profile() -> CloudConfig:
    """A synthetic cloud-demo profile: synthetic data, restricted API, no creds."""
    return CloudConfig.from_dict({
        "mode": "cloud_demo",
        "synthetic_data_only": True,
        "restricted_api": True,
        "cloud_services": {s: "local" for s in (
            "database", "object_storage", "queue_event_transport",
            "secrets", "identity", "observability", "scheduled_jobs",
            "model_providers",
        )},
        "credentials": {},
        "usage_limits": {"max_requests": 1000, "max_records": 10000, "budget_usd": 0.50},
    })
