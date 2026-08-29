"""Provider-neutral connector registry.

The registry is the single entry point for obtaining a connector. It is
credential-neutral: in the first version only `mode="fake"` is accepted. Live
adapters are *documented* (see LIVE_ADAPTER_CONTRACT.md) but intentionally not
activatable yet, so no live credentials can be loaded accidentally.

Known providers: zendesk, salesforce, clay.
"""
from __future__ import annotations

from typing import Mapping

from .base import BaseConnector
from .contracts import ConnectorContext
from .fakes import build_demo_connectors

KNOWN_PROVIDERS = ("salesforce", "zendesk", "clay")
SUPPORTED_MODES = ("fake",)


class ConnectorRegistry:
    def __init__(self, mode: str = "fake") -> None:
        mode = (mode or "").strip().lower()
        if mode not in SUPPORTED_MODES:
            raise ValueError(
                f"unsupported connector mode: {mode!r}; "
                f"live adapters are not enabled yet (supported={SUPPORTED_MODES})"
            )
        self.mode = mode

    def get_connector(self, provider: str, context: ConnectorContext) -> BaseConnector:
        provider = (provider or "").strip().lower()
        if provider not in KNOWN_PROVIDERS:
            raise ValueError(f"unknown or unsupported provider: {provider!r} (known={KNOWN_PROVIDERS})")
        # build_demo_connectors is credential-neutral and returns all three;
        # we surface only the requested one.
        return build_demo_connectors(context)[provider]

    def list_providers(self) -> tuple[str, ...]:
        return KNOWN_PROVIDERS


def build_connectors(context: ConnectorContext, mode: str = "fake") -> Mapping[str, BaseConnector]:
    """Convenience: build every known connector for a context."""
    registry = ConnectorRegistry(mode=mode)
    return {p: registry.get_connector(p, context) for p in KNOWN_PROVIDERS}
