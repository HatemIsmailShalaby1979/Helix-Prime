"""Helix Codex cloud-ready, local-first boundary (Prompt 9).

Provider-neutral interfaces + local adapters + a synthetic cloud-demo profile.
Local execution is primary; cloud adapters are intentionally absent so any
non-local request fails safe.
"""
from __future__ import annotations

from .errors import SafeFailure
from .interfaces import (
    Database, ObjectStorage, EventTransport, SecretsStore, IdentityProvider,
    Observability, Scheduler, ModelProvider,
)
from .config import CloudConfig, UsageLimits, demo_profile
from .profile import (
    CloudProvider, DemoController, SpendControl,
    optional_cloud_services, SPEND_CONTROL_DOCS,
)

__all__ = [
    "SafeFailure",
    "Database", "ObjectStorage", "EventTransport", "SecretsStore",
    "IdentityProvider", "Observability", "Scheduler", "ModelProvider",
    "CloudConfig", "UsageLimits", "demo_profile",
    "CloudProvider", "DemoController", "SpendControl",
    "optional_cloud_services", "SPEND_CONTROL_DOCS",
]
