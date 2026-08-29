# 6. Memory Model

Memory is an **append-only, hash-chained ledger** (`memory.governed_memory.GovernedMemory`).
It is the system of record for decisions, recommendations, approvals, outcomes, failures,
corrections, policies, customer context, and workflow history.

## Properties
- **Append-only:** records are never updated or deleted; transitions (e.g. approval → rolled_back)
  append a new versioned record with `supersedes`. This preserves the audit trail.
- **Hash-chained:** each record links to the previous hash; `verify_chain()` validates integrity.
- **Tenant-scoped:** `retrieve(tenant_id=...)` isolates clients; cross-tenant reads are refused.
- **Provenance-bearing:** every record carries correlation ID, data mode, basis, and source refs.
- **Typed kinds/natures:** decision / recommendation / approval / outcome / failure / correction /
  policy / customer_context / workflow_history, with natures (verified_fact, user_claim,
  model_inference, simulated_event, historical_event, verified_outcome).

## Retention
`apply_retention(as_of)` **flags** records whose `retention_until` has passed (`retention_status="expired"`)
and excludes them from default retrieval. It does **not** drop records — deletion is never silent.

## What is demonstrated
- The synthetic demo records 41 governed records across two tenants with `audit_chain_intact=True`.
- Retention handling is verified by a test that flags an expired record and asserts it is not dropped.
- Rollback appends an incident record and marks the approval `rolled_back`.

## Limitation (see 11_known_limitations.md)
In this build `GovernedMemory` is **in-memory** by default (`audit_status()` may report
`in_memory_not_persisted`). A durable, hardened store (e.g. the `control_plane.store` SQLite
path used by release gates) is available in the wider platform but is not wired into the
pilot/capability runtime here. Persistence and backup/restore are demonstrated at the release-gate
level, not yet at the pilot runtime level.
