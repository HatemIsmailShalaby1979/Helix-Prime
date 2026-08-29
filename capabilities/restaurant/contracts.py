"""Restaurant connector contracts (Prompt 11, items 3 & 6).

The restaurant connector reuses :class:`connectors.base.BaseConnector` so it inherits
the governed behaviors every connector MUST share: tenant/client scope enforcement,
deterministic rate-limit/retry, typed failure envelope, provenance + correlation_id on
every read, and write gating. It is read-only by construction: ``request_write`` returns
``executed=False`` (inherited from the base). No live adapter is activated.
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence

from connectors.base import BaseConnector
from connectors.contracts import (
    ConnectorCapability,
    ConnectorContext,
    ConnectorResult,
    ConnectorStatus,
    _now,
)


class RestaurantConnector(BaseConnector):
    """Synthetic, read-only source for one restaurant location's operational data."""

    def __init__(self, connector_id: str, provider: str, fixtures: Mapping[str, Any]) -> None:
        super().__init__(connector_id, provider, status=ConnectorStatus.HEALTHY)
        self._fixtures = dict(fixtures)

    # ----------------------------------------------------------------- capabilities
    def capabilities(self) -> Sequence[ConnectorCapability]:
        return (ConnectorCapability(
            connector_id=self.connector_id,
            provider=self.provider,
            capability_id="restaurant_read",
            reads=("shifts", "inventory", "suppliers", "complaints", "daily_summary"),
            writes=("reorder", "notify_staff"),
            risk_class="client_confidential",
            writes_require_approval=True,
            approval_required=True,
        ),)

    # -------------------------------------------------------------- scope-filtered fetchers
    def _scope_ok(self, ctx: ConnectorContext, obj: Any) -> bool:  # type: ignore[override]
        return obj.tenant_id == ctx.tenant_id and obj.client_id == ctx.client_id

    def _fetch_shifts(self, ctx: ConnectorContext) -> Sequence[Any]:
        return [s for s in self._fixtures.get("shifts", []) if self._scope_ok(ctx, s)]

    def _fetch_inventory(self, ctx: ConnectorContext) -> Sequence[Any]:
        return [i for i in self._fixtures.get("inventory", []) if self._scope_ok(ctx, i)]

    def _fetch_suppliers(self, ctx: ConnectorContext) -> Sequence[Any]:
        return [s for s in self._fixtures.get("suppliers", []) if self._scope_ok(ctx, s)]

    def _fetch_complaints(self, ctx: ConnectorContext) -> Sequence[Any]:
        return [c for c in self._fixtures.get("complaints", []) if self._scope_ok(ctx, c)]

    def _fetch_daily_summary(self, ctx: ConnectorContext) -> Sequence[Any]:
        return [d for d in self._fixtures.get("daily_summary", []) if self._scope_ok(ctx, d)]

    # ---------------------------------------------------------------- public read paths
    def list_shifts_result(self, ctx: ConnectorContext) -> ConnectorResult:
        if self._status in (ConnectorStatus.REVOKED, ConnectorStatus.DISCONNECTED):
            return self._unavailable_result(ctx)
        if self._rate_limited():
            return self._rate_limited_result(ctx)
        data = tuple(self._fetch_shifts(ctx))
        return ConnectorResult(status="ok", data=data,
                               provenance=self._provenance(ctx, len(data)),
                               correlation_id=ctx.correlation_id)

    def list_shifts(self, ctx: ConnectorContext) -> Sequence[Any]:
        return self.list_shifts_result(ctx).data or ()

    def list_inventory_result(self, ctx: ConnectorContext) -> ConnectorResult:
        if self._status in (ConnectorStatus.REVOKED, ConnectorStatus.DISCONNECTED):
            return self._unavailable_result(ctx)
        if self._rate_limited():
            return self._rate_limited_result(ctx)
        data = tuple(self._fetch_inventory(ctx))
        return ConnectorResult(status="ok", data=data,
                               provenance=self._provenance(ctx, len(data)),
                               correlation_id=ctx.correlation_id)

    def list_inventory(self, ctx: ConnectorContext) -> Sequence[Any]:
        return self.list_inventory_result(ctx).data or ()

    def list_suppliers_result(self, ctx: ConnectorContext) -> ConnectorResult:
        if self._status in (ConnectorStatus.REVOKED, ConnectorStatus.DISCONNECTED):
            return self._unavailable_result(ctx)
        if self._rate_limited():
            return self._rate_limited_result(ctx)
        data = tuple(self._fetch_suppliers(ctx))
        return ConnectorResult(status="ok", data=data,
                               provenance=self._provenance(ctx, len(data)),
                               correlation_id=ctx.correlation_id)

    def list_suppliers(self, ctx: ConnectorContext) -> Sequence[Any]:
        return self.list_suppliers_result(ctx).data or ()

    def list_complaints_result(self, ctx: ConnectorContext) -> ConnectorResult:
        if self._status in (ConnectorStatus.REVOKED, ConnectorStatus.DISCONNECTED):
            return self._unavailable_result(ctx)
        if self._rate_limited():
            return self._rate_limited_result(ctx)
        data = tuple(self._fetch_complaints(ctx))
        return ConnectorResult(status="ok", data=data,
                               provenance=self._provenance(ctx, len(data)),
                               correlation_id=ctx.correlation_id)

    def list_complaints(self, ctx: ConnectorContext) -> Sequence[Any]:
        return self.list_complaints_result(ctx).data or ()

    def list_daily_summary_result(self, ctx: ConnectorContext) -> ConnectorResult:
        if self._status in (ConnectorStatus.REVOKED, ConnectorStatus.DISCONNECTED):
            return self._unavailable_result(ctx)
        if self._rate_limited():
            return self._rate_limited_result(ctx)
        data = tuple(self._fetch_daily_summary(ctx))
        return ConnectorResult(status="ok", data=data,
                               provenance=self._provenance(ctx, len(data)),
                               correlation_id=ctx.correlation_id)

    def list_daily_summary(self, ctx: ConnectorContext) -> Sequence[Any]:
        return self.list_daily_summary_result(ctx).data or ()


def build_restaurant_connectors(context: ConnectorContext, fixtures: Mapping[str, Any]) -> dict:
    """One read-only connector per restaurant location (keyed by provider name)."""
    return {"restaurant_ops": RestaurantConnector("restaurant_ops", "RestaurantOps", fixtures)}
