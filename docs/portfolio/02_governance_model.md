# 2. Governance Model

Governance is **evidence-based and code-enforced**, not narrative. A claim in the
implementation baseline must be backed by a passing test.

## Constitutional anchors
- `00_CONSTITUTION.md` — "Identity must precede implementation", "Truth is paramount",
  "Architecture serves as the expression of truth". The governance check asserts these
  principles are present.
- `MASTER_STORY.md` — chronological, factual log of what was built and verified; references
  the Constitution as authority.
- `GOVERNANCE/IMPLEMENTATION_MATRIX.md` — the authoritative Phase-1 baseline. Each delivered
  item lists the module + the test that verifies it. Total: **445 tests pass**.

## Automated governance check
`python3 -m GOVERNANCE.governance_check check` verifies:
- Constitution contains the required principles.
- `MASTER_STORY.md` references the Constitution.
- No stale authority references (e.g. `ROOT_BOOT.md`, `constitution_v0.md`).
Result: **`governance=PASS`**.

## Release gates (C8)
`release/gate.py` runs a profile of gates and classifies deterministically. Only two
final classifications are permitted: `CONTROLLED_PILOT_READY` and
`PRODUCTION_CANDIDATE`. An unqualified `PRODUCTION` label is **never** emitted.
- `controlled_pilot` → `CONTROLLED_PILOT_READY` (all gates green).
- `production` → `NOT_READY`: production-only gates are intentionally red (require external
  signed production evidence, certified isolation, external observer audit, security/legal
  review, etc.) and cannot be satisfied by a local automated run.

This is by design: the system fails closed on any production claim it cannot evidence.

## Deny-by-default authorization
`security.policy.authorize` denies any unknown capability. The release security gate
probes an `__unknown_capability` and asserts denial. See
[04_security_model.md](04_security_model.md).

## Separation of duties
Approvals require a cross-actor, cross-role decision (`pilot.approval.evaluate_approval_decision`
and `metacognition.improvement.MetacognitionEngine.approve` both reject self/same-role).
