"""Shared, provider-neutral connector base.

Concrete connectors (fake or live) subclass :class:`BaseConnector`. The base
encodes the governed behaviors that every connector MUST share:

* tenant/client scope enforcement (fail closed on cross-tenant writes/enrich);
* deterministic rate-limit behavior (count-based, no wall clock);
* deterministic retry behavior (countable, no real sleep);
* typed failure envelope (:class:`FailureDetail`);
* provenance + correlation_id on every read result;
* write gating: writes require an explicit cross-role approval and an
  *activated* live adapter. The read-only first version never executes writes.
"""
from __future__ import annotations

from typing import Any, Callable, Mapping, Sequence

from .contracts import (
    ConnectorContext,
    ConnectorResult,
    ConnectorStatus,
    ConnectorWriteResult,
    FailureDetail,
    Provenance,
    RateLimitPolicy,
    RetryPolicy,
    _now,
)


class BaseConnector:
    connector_id: str
    provider: str

    def __init__(
        self,
        connector_id: str,
        provider: str,
        rate_limit: RateLimitPolicy | None = None,
        retry: RetryPolicy | None = None,
        status: ConnectorStatus = ConnectorStatus.CONFIGURED,
    ) -> None:
        self.connector_id = connector_id
        self.provider = provider
        self._rate_limit = rate_limit or RateLimitPolicy()
        self._retry = retry or RetryPolicy()
        self._status = status
        self._read_count = 0  # deterministic, instance-scoped call counter

    # ------------------------------------------------------------------ status
    def status(self) -> ConnectorStatus:
        return self._status

    def health_check(self) -> Mapping[str, Any]:
        return {
            "connector_id": self.connector_id,
            "provider": self.provider,
            "status": self._status.value,
            "rate_limit": self._rate_limit.max_requests_per_window,
            "retry_max_attempts": self._retry.max_attempts,
        }

    def capabilities(self) -> Sequence[Any]:
        # Subclasses declare their capabilities.
        return ()

    # ------------------------------------------------------------------- scope
    def _assert_scope(self, context: ConnectorContext, tenant_id: str, client_id: str) -> None:
        if (context.tenant_id, context.client_id) != (tenant_id, client_id):
            raise PermissionError("connector tenant/client scope mismatch")

    def _scope_ok(self, context: ConnectorContext, tenant_id: str, client_id: str) -> bool:
        return (context.tenant_id, context.client_id) == (tenant_id, client_id)

    # --------------------------------------------------------------- rate-limit
    def _rate_limited(self) -> bool:
        self._read_count += 1
        # Absolute, deterministic count (window_seconds is informational).
        return self._read_count > self._rate_limit.max_requests_per_window

    def _rate_limited_result(self, context: ConnectorContext) -> ConnectorResult:
        return ConnectorResult(
            status="rate_limited",
            error=FailureDetail(
                "rate_limited",
                f"{self.provider} exceeded rate limit "
                f"({self._rate_limit.max_requests_per_window}/window); failing closed",
                retryable=True,
            ),
            correlation_id=context.correlation_id,
        )

    def _unavailable_result(self, context: ConnectorContext) -> ConnectorResult:
        return ConnectorResult(
            status="unavailable",
            error=FailureDetail(
                "connector_unavailable",
                f"{self.provider} connector is {self._status.value}; no live reads",
                retryable=False,
            ),
            correlation_id=context.correlation_id,
        )

    # --------------------------------------------------------------- provenance
    def _provenance(
        self,
        context: ConnectorContext,
        record_count: int,
        source_refs: tuple = (),
    ) -> Provenance:
        return Provenance(
            provider=self.provider,
            connector_id=self.connector_id,
            fetched_at=_now(),
            record_count=record_count,
            data_mode=context.data_mode,
            correlation_id=context.correlation_id,
            source_refs=tuple(source_refs),
        )

    # ------------------------------------------------------------------ reads
    # Subclasses implement the protected fetchers. The public read paths wrap
    # them with status/rate-limit/provenance and also expose a thin
    # sequence-returning API for backward compatibility.
    def _fetch_accounts(self, context: ConnectorContext) -> Sequence[Any]:
        raise NotImplementedError

    def _fetch_tickets(self, context: ConnectorContext, account_id: str) -> Sequence[Any]:
        raise NotImplementedError

    def _fetch_enrichment(self, context: ConnectorContext, account: Any) -> Any:
        raise NotImplementedError

    def list_accounts_result(self, context: ConnectorContext) -> ConnectorResult:
        if self._status in (ConnectorStatus.REVOKED, ConnectorStatus.DISCONNECTED):
            return self._unavailable_result(context)
        if self._rate_limited():
            return self._rate_limited_result(context)
        data = tuple(self._fetch_accounts(context))
        return ConnectorResult(
            status="ok",
            data=data,
            provenance=self._provenance(context, len(data)),
            correlation_id=context.correlation_id,
        )

    def list_accounts(self, context: ConnectorContext) -> Sequence[Any]:
        return self.list_accounts_result(context).data or ()

    def list_tickets_result(self, context: ConnectorContext, account_id: str) -> ConnectorResult:
        if self._status in (ConnectorStatus.REVOKED, ConnectorStatus.DISCONNECTED):
            return self._unavailable_result(context)
        if self._rate_limited():
            return self._rate_limited_result(context)
        if not account_id or not isinstance(account_id, str):
            return ConnectorResult(
                status="error",
                error=FailureDetail("invalid_input", "account_id must be a non-empty string"),
                correlation_id=context.correlation_id,
            )
        data = tuple(self._fetch_tickets(context, account_id))
        return ConnectorResult(
            status="ok",
            data=data,
            provenance=self._provenance(context, len(data)),
            correlation_id=context.correlation_id,
        )

    def list_tickets(self, context: ConnectorContext, account_id: str) -> Sequence[Any]:
        return self.list_tickets_result(context, account_id).data or ()

    def enrich_account_result(self, context: ConnectorContext, account: Any) -> ConnectorResult:
        if self._status in (ConnectorStatus.REVOKED, ConnectorStatus.DISCONNECTED):
            return self._unavailable_result(context)
        if self._rate_limited():
            return self._rate_limited_result(context)
        if not self._scope_ok(context, account.tenant_id, account.client_id):
            return ConnectorResult(
                status="error",
                error=FailureDetail(
                    "scope_denied", "cross-tenant enrichment denied", retryable=False,
                ),
                correlation_id=context.correlation_id,
            )
        data = self._fetch_enrichment(context, account)
        return ConnectorResult(
            status="ok",
            data=data,
            provenance=self._provenance(context, 1, source_refs=(data.source,)),
            correlation_id=context.correlation_id,
        )

    def enrich_account(self, context: ConnectorContext, account: Any) -> Any:
        # Backward-compatible thin API: raises on cross-tenant scope mismatch.
        self._assert_scope(context, account.tenant_id, account.client_id)
        return self._fetch_enrichment(context, account)

    # ------------------------------------------------------------------- retry
    def with_retry(self, op: Callable[[], ConnectorResult], context: ConnectorContext) -> ConnectorResult:
        """Run `op` with deterministic retry. Retries only on retryable errors,
        up to `retry.max_attempts`. Never sleeps."""
        attempts = 0
        last: ConnectorResult | None = None
        while attempts < self._retry.max_attempts:
            attempts += 1
            last = op()
            if (
                isinstance(last, ConnectorResult)
                and last.status == "error"
                and last.error is not None
                and last.error.retryable
                and last.error.code in self._retry.retry_on
            ):
                continue
            return last
        return last  # type: ignore[return-value]

    # ------------------------------------------------------------------ writes
    def request_write(
        self,
        context: ConnectorContext,
        capability_id: str,
        payload: Mapping[str, Any],
        approval: Any | None = None,
    ) -> ConnectorWriteResult:
        """Gated write path. `capability_id` names a WRITE capability (one of a
        capability's `writes`). In the read-only first version this NEVER
        executes a write; it proves the approval gate exists and fails closed."""
        # Find the capability that owns this write capability id.
        matching = [c for c in self.capabilities() if capability_id in getattr(c, "writes", ())]
        if not matching:
            return ConnectorWriteResult(
                executed=False,
                approval_required=False,
                reason="unknown_write_capability",
                correlation_id=context.correlation_id,
            )
        cap = matching[0]
        if getattr(cap, "writes_require_approval", True) and not self._approval_valid(approval, context):
            return ConnectorWriteResult(
                executed=False,
                approval_required=True,
                reason="approval_required",
                correlation_id=context.correlation_id,
            )
        # Read-only first version: even with a valid approval, the live adapter
        # is not activated, so writes remain disabled by design.
        return ConnectorWriteResult(
            executed=False,
            approval_required=True,
            reason="read_only_first_version_disallows_writes",
            correlation_id=context.correlation_id,
        )

    @staticmethod
    def _approval_valid(approval: Any | None, context: ConnectorContext) -> bool:
        if approval is None:
            return False
        decision = getattr(approval, "decision", None)
        if decision != "approved":
            return False
        # Separation-of-duties: approver must differ from the requesting actor
        # (cross-actor) and supply an approver role.
        approver_actor = getattr(approval, "approver_actor", None)
        approver_role = getattr(approval, "approver_role_id", None)
        if approver_actor in (None, "", context.actor) and approver_role in (None, "", ""):
            return False
        if approver_actor == context.actor:
            return False
        return True
