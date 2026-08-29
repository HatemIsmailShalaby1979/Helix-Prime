# 5. Evidence Model

"Evidence" means every claim is traceable to a recorded, provenance-bearing artifact in
governed memory, and the chain of those artifacts verifies.

## Record-level provenance
Every GovernedMemory record carries tenant_id, client_id, correlation_id, data_mode
(historical_consented / simulated_realistic / live_customer; never live_customer here),
provenance {correlation_id, data_mode, basis, sources}, evidence_refs, nature, and
classification.

## Audit chain
Records are append-only and hash-chained (mem.verify_chain() returns (bool, msg)).
audit_status() reports verified / in_memory_not_persisted / broken. The synthetic demo and
all tests assert audit_chain_intact is True.

## Approval evidence
Each committal action produces a recommendation (with evidence) and an approval in draft.
Approving/denying/rolling-back appends a new, versioned approval record (supersedes the
prior); the original ledger line is never mutated. approval_state is always visible
(draft/approved/denied/rolled_back).

## Evidence pack
pilot.evidence_pack.build_evidence_pack and RestaurantCapabilityPack.build_evidence_pack
assemble scope, consent, config, data-mode breakdown, live-customer-record count, metrics,
baseline, approval summary, incidents, audit status, audit-chain result, and a final status
(pilot/pack ready, design-partner approval pending, production readiness NOT_ESTABLISHED).

## Metacognitive evidence
Improvement proposals are recorded as governed policy records with applied=False and an
evidence report (hypothesis, evaluation results, risk, rollback plan). They are proposed and
evaluated, never silently applied.

## Governance evidence
GOVERNANCE/IMPLEMENTATION_MATRIX.md ties every delivered item to a test; the governance check
and release gates are themselves recorded evidence.
