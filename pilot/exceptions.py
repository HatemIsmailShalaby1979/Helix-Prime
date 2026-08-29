"""Pilot-specific errors (Prompt 10)."""
from __future__ import annotations


class PilotError(Exception):
    """Raised on any pilot policy violation (consent, config, approval)."""
