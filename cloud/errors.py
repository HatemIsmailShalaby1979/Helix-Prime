"""Safe-failure errors for the cloud-ready, local-first boundary (Prompt 9)."""
from __future__ import annotations


class SafeFailure(Exception):
    """Raised when a cloud-ready operation cannot proceed safely.

    Never swallowed silently: it signals a degraded/offline-safe condition
    (missing cloud service, live credentials in a demo profile, budget exceeded,
    restricted operation, or a shut-down provider). Local execution is always
    the safe default.
    """
