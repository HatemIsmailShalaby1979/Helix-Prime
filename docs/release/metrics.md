# Helix Prime Codex C8 — Operational Metrics

Status: metrics for the controlled pilot. Machine implementation:
`release/pilot_metrics.py`. Feed source: `scripts/pilot_dry_run.py`.

## Three distinct kinds of value (never conflated)

1. **Measured** — values actually produced by the SYNTHETIC dry-run.
2. **Proposed pilot thresholds** — candidate operating thresholds for a real
   pilot; NOT validated targets and NOT asserted as requirements.
3. **Production SLOs** — explicitly NOT validated; never claimed by a pilot.

## Measured (from the dry-run)

- `workflow_completion_rate`
- `approval_denial_rate`
- `timeout_rate`
- `retry_rate`
- `dead_letter_rate`
- `audit_verification_rate`
- `data_classification_violations` (count)
- `tenant_isolation_violations` (count)
- `model_unavailable_count` (count)
- `sibling_transport_failures` (count)
- `exec_time_ms_mean / p50 / p95 / p99 / stddev`

Rates are 0.0–1.0; counts are integers. Aggregation only — no targets applied.

## Proposed pilot thresholds (not validated) and production SLOs (not claimed)

Recorded in `PROPOSED_PILOT_THRESHOLDS` and `PRODUCTION_SLOS_NOT_VALIDATED`.
Most are `None` (not set) because they require real-pilot or external evidence.
Where a placeholder is set (e.g. zero data-classification/tenant-isolation
violations, 100% audit verification), it expresses an expectation, not a claim.

## How to read a dry-run metrics block

See the `metrics` object in `evidence/pilot/<timestamp>/pilot-metrics.json`.
Its top-level keys are `measured_synthetic_dry_run`, `proposed_pilot_thresholds`,
and `production_slos_not_validated`, plus a note clarifying that measured values
are synthetic only and that no production SLO is claimed.
