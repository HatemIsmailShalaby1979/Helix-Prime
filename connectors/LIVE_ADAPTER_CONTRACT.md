# Live Adapter Contract (deferred — first version is read-only & credential-neutral)

The first connector version is **read-only and credential-neutral**: the
in-repo `FakeConnector`s return synthetic-but-realistic data and never contact
a live provider or execute a write. This document specifies the contract a
**future live adapter** must satisfy before it can be activated. It is
deliberately *not* implemented yet so that no live credentials can be loaded
by accident.

## Activation gate

A live adapter may ONLY be constructed when:

1. `ConnectorRegistry(mode="live")` is explicitly requested (today this raises
   `ValueError` — the mode is unsupported until the gate below passes);
2. the provider's credentials are supplied **only** via environment variables
   or a secrets manager referenced by environment configuration — **never**
   hardcoded, never committed, never read from a URL, fixture, log, or doc;
3. a governance check confirms the credential is absent from source control
   (`security/secret_scan` style gate); and
4. a human approval record exists for enabling the live integration.

Until all four hold, `request_write(...)` and live reads remain disabled.

## Interface a live adapter must implement

A live adapter subclasses `connectors.base.BaseConnector` and therefore MUST:

- expose `connector_id` and `provider`;
- implement `capabilities()` returning `ConnectorCapability` rows whose
  `reads`/`writes`, `data_classification`, `rate_limit`, `retry`, and
  `approval_required` accurately reflect the real provider;
- implement `_fetch_accounts`, `_fetch_tickets`, `_fetch_enrichment`
  (the base wraps them with scope/rate-limit/retry/provenance);
- return `ConnectorResult` envelopes (never raise for ordinary failures —
  use `status="error"` + `FailureDetail`);
- raise `PermissionError` on cross-tenant scope mismatch for writes/enrichment,
  and silently return empty for cross-tenant reads (no leak).

## Credential handling (non-negotiable)

- Credentials enter only through constructor parameters bound to environment
  configuration at runtime (e.g. `os.environ["ZENDESK_TOKEN"]` injected by the
  deploy), never from literals in source.
- Missing credentials MUST fail closed: `status()` returns `UNCONFIGURED` and
  reads return `ConnectorResult(status="unavailable")`. The connector must not
  fall back to a fake or to any other tenant.
- No credential, token, bearer, or API key may appear in source, URLs,
  fixtures, logs, or documentation.

## Rate-limit behavior

- Honor the provider's `Retry-After` / `X-RateLimit-*` headers; map exhaustion
  to `ConnectorResult(status="rate_limited", error=FailureDetail("rate_limited", ..., retryable=True))`.
- `RateLimitPolicy.on_exceed` defaults to `fail_closed`. A live adapter may
  implement `throttle` only if it backs off per the provider's headers.

## Retry behavior

- `RetryPolicy.max_attempts` and `retry_on` govern retries. Retries apply ONLY
  to `retryable=True` failures whose `code` is in `retry_on`
  (`transient`, `rate_limited`). Non-retryable failures return immediately.
- Real backoff uses `RetryPolicy.backoff_seconds`; the deterministic test path
  does not sleep.

## Failure behavior

- Every abnormal outcome is a typed `FailureDetail(code, message, retryable)`.
- `transient`/`rate_limited` → retryable. `auth`/`forbidden`/`invalid_input`/
  `connector_unavailable` → not retryable.

## Write behavior (approval-gated)

- A write capability (`writes` non-empty) sets `writes_require_approval=True`
  and `approval_required=True`.
- `request_write(context, capability_id, payload, approval)` MUST:
  1. reject unknown write capabilities (`reason="unknown_write_capability"`);
  2. refuse without a valid approval (`reason="approval_required"`);
  3. validate the approval for separation-of-duties (approver != requester,
     approver role present) — the canonical `contracts.task.Approval` satisfies
     this;
  4. only then, with an *activated* live adapter, perform the write and return
     `ConnectorWriteResult(executed=True, ...)`.
- The read-only first version never reaches step 4.

## Provenance & data mode

- Every `ConnectorResult.provenance` carries `provider`, `connector_id`,
  `fetched_at`, `record_count`, `data_mode`, `correlation_id`, and
  `source_refs`.
- Live external data MUST set `ConnectorContext.data_mode = "live_external"`
  and tag `SourceRef.data_mode` accordingly, so it is never confused with
  `simulated_realistic` data.
