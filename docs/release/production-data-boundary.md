# Production data boundary

Status: binding. This document separates two things that must never be
confused: production readiness of the general app, and readiness of the
sports-academy capability pack.

## General app: real data only after the production gates

The app records real account and collaboration data (user claims, memory,
tasks) under human operation. That data may be treated as production data
only after every production gate passes — signed production evidence,
certified isolation, external audit, deployment architecture, disaster
recovery, ownership, security and legal review
(`docs/release/production-blockers.md`, all currently `OPEN`).

Until then the enforceable boundary is:

- The release gate never emits an unqualified `PRODUCTION` label, and the
  go/no-go record stays scoped to `SYNTHETIC_OR_CONSENTED_ONLY`. Any other
  scope fails the data-boundary test suite.
- Every governed record carries the full envelope — tenant_id, client_id,
  correlation_id, data_mode, provenance (basis, sources), evidence_refs,
  classification — enforced at the writer (`helix_codex_app/db.py::
  record_node`, `memory/governed_memory.py::add`), never by convention.
- A `verified_fact` or `verified_outcome` is refused without
  `evidence_refs`: no model-generated result is ever recorded as a
  verified outcome without evidence.
- Live external connectors stay disabled unless separately approved
  (`connectors` fail closed on live activation; the release gate pins
  synthetic-or-consented data).

## Sports-academy pack: synthetic, read-only, not established

The Scoach academy pack is a step further from production than the app,
by design, for this sprint:

- `DATA_MODE = "simulated_realistic"` pinned in
  `capabilities/sports_academy/fixtures.py`; every fixture `SourceRef`
  carries it, and `AcademyConnector._list_result` — the single funnel for
  all nine reads — raises on any record stamped with another mode, so
  live data cannot flow in accidentally.
- `production_readiness = "NOT_ESTABLISHED"` in the pack metadata; the
  registry-level readiness contract admits no other value.
- Connectors are read-only (`writes=()`); no live Scoach connector exists
  in this sprint, and the pack tree carries no network client imports
  (asserted by test).
- Graduation is a separate, future decision: consented roster import,
  client-defined curriculum, explicit readiness review, and the same
  production gates as above. Nothing in this sprint pre-authorizes it.
