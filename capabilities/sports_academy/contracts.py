"""Academy connector contracts (v1).

The academy connector reuses :class:`connectors.base.BaseConnector` so it
inherits the governed behaviors every connector MUST share: tenant/client scope
enforcement, deterministic rate-limit/retry, typed failure envelope, provenance +
correlation_id on every read, and write gating. It is read-only by construction:
``request_write`` returns ``executed=False`` (inherited from the base). No live
adapter is activated.
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence

from connectors.base import BaseConnector
from connectors.contracts import (
    ConnectorCapability,
    ConnectorContext,
    ConnectorResult,
    ConnectorStatus,
)


class AcademyConnector(BaseConnector):
    """Synthetic, read-only source for one sports academy location's data."""

    def __init__(self, connector_id: str, provider: str, fixtures: Mapping[str, Any]) -> None:
        super().__init__(connector_id, provider, status=ConnectorStatus.HEALTHY)
        self._fixtures = dict(fixtures)

    # ----------------------------------------------------------------- capabilities
    def capabilities(self) -> Sequence[ConnectorCapability]:
        return (
            ConnectorCapability(
                connector_id=self.connector_id,
                provider=self.provider,
                capability_id="academy_read",
                reads=(
                    "athletes",
                    "families",
                    "coaches",
                    "programs",
                    "sessions",
                    "checkins",
                    "facility_slots",
                    "fee_payments",
                    "enrollment_records",
                ),
                writes=(),
                risk_class="client_confidential",
                writes_require_approval=True,
                approval_required=True,
            ),
        )

    # -------------------------------------------------------------- scope-filtered fetchers
    def _scope_ok(self, ctx: ConnectorContext, obj: Any) -> bool:  # type: ignore[override]
        return obj.tenant_id == ctx.tenant_id and obj.client_id == ctx.client_id

    def _fetch(self, ctx: ConnectorContext, key: str) -> Sequence[Any]:
        return [o for o in self._fixtures.get(key, []) if self._scope_ok(ctx, o)]

    # ---------------------------------------------------------------- public read paths
    def _list_result(self, ctx: ConnectorContext, key: str) -> ConnectorResult:
        if self._status in (ConnectorStatus.REVOKED, ConnectorStatus.DISCONNECTED):
            return self._unavailable_result(ctx)
        if self._rate_limited():
            return self._rate_limited_result(ctx)
        data = tuple(self._fetch(ctx, key))
        self._reject_live_data(data)
        return ConnectorResult(
            status="ok",
            data=data,
            provenance=self._provenance(ctx, len(data)),
            correlation_id=ctx.correlation_id,
        )

    def _reject_live_data(self, data: Sequence[Any]) -> None:
        from capabilities.sports_academy.fixtures import DATA_MODE

        for obj in data:
            mode = getattr(getattr(obj, "source", None), "data_mode", None)
            if mode != DATA_MODE:
                raise ValueError(
                    "academy connector refused non-simulated data "
                    f"(data_mode={mode!r}); the pack runs simulated_realistic only"
                )

    def list_athletes(self, ctx: ConnectorContext) -> Sequence[Any]:
        return self._list_result(ctx, "athletes").data or ()

    def list_families(self, ctx: ConnectorContext) -> Sequence[Any]:
        return self._list_result(ctx, "families").data or ()

    def list_coaches(self, ctx: ConnectorContext) -> Sequence[Any]:
        return self._list_result(ctx, "coaches").data or ()

    def list_programs(self, ctx: ConnectorContext) -> Sequence[Any]:
        return self._list_result(ctx, "programs").data or ()

    def list_sessions(self, ctx: ConnectorContext) -> Sequence[Any]:
        return self._list_result(ctx, "sessions").data or ()

    def list_checkins(self, ctx: ConnectorContext) -> Sequence[Any]:
        return self._list_result(ctx, "checkins").data or ()

    def list_facility_slots(self, ctx: ConnectorContext) -> Sequence[Any]:
        return self._list_result(ctx, "facility_slots").data or ()

    def list_fee_payments(self, ctx: ConnectorContext) -> Sequence[Any]:
        return self._list_result(ctx, "fee_payments").data or ()

    def list_enrollment_records(self, ctx: ConnectorContext) -> Sequence[Any]:
        return self._list_result(ctx, "enrollment_records").data or ()


def build_academy_connectors(context: ConnectorContext, fixtures: Mapping[str, Any]) -> dict:
    """One read-only connector per academy location (keyed by provider name)."""
    return {"academy_ops": AcademyConnector("academy_ops", "AcademyOps", fixtures)}
