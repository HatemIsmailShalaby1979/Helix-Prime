# 14. Technical Decision Log

Key decisions, with rationale and trade-off. All are implemented and tested in-repo.

## D1 — Read-only-first connectors
Connectors return synthetic data and `request_write` returns `executed=False` by design.
*Rationale:* never take uncontrolled action; prove the approval gate exists without risk.
*Trade-off:* no real automation yet; acceptable for a controlled pilot.

## D2 — Append-only, hash-chained memory
`GovernedMemory` never updates/deletes; transitions append versioned records.
*Rationale:* non-repudiable audit trail; verify_chain integrity.
*Trade-off:* storage growth; mitigated by retention-flag (never drop) and future durable store.

## D3 — Separation of duties on approvals
Self/same-role approval denied in `pilot.approval` and `metacognition.improvement`.
*Rationale:* accountable, human-controlled committal actions.
*Trade-off:* slower; required for governance.

## D4 — No automatic self-improvement
Metacognition proposes/evaluates but deployment is explicit and gated (`apply_proposal` never called
by the engine).
*Rationale:* "improves through evidence without silently taking control."
*Trade-off:* improvement is manual until a reviewed pipeline exists (roadmap).

## D5 — Local-first cloud boundary
Cloud is provider-neutral interfaces + local adapters + synthetic-only demo profile; fails safe closed.
*Rationale:* zero infra cost, no live creds, demonstrable offline.
*Trade-off:* no real cloud path yet; production cloud is future work.

## D6 — Capability-pack pattern (reuse, not fork)
A pack adds ontology/roles/workflows/policies and reuses the core; no separate platform.
*Rationale:* one governed core for many businesses; demonstrated with call-centre + restaurant in one memory.
*Trade-off:* packs must conform to core contracts.

## D7 — Consent + explicit data modes
`historical_consented` / `simulated_realistic` / `live_customer`; live never activated here.
*Rationale:* unambiguous provenance; synthetic is never mistaken for live.
*Trade-off:* limits demo to synthetic/historical data.

## D8 — Governance-as-code
`IMPLEMENTATION_MATRIX.md` ties every item to a test; `governance_check` + `release.gate` enforce it.
*Rationale:* claims require evidence; fail closed on production.
*Trade-off:* maintenance overhead; worth it for accountability.

## D9 — Retention flags, never drops
`apply_retention` marks `expired`, excludes from default retrieve; no silent deletion.
*Rationale:* comply with deletion requests without breaking audit history.
*Trade-off:* expired records linger (by design).
