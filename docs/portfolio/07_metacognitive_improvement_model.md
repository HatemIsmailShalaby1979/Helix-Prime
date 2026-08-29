# 7. Metacognitive Improvement Model

Metacognition here is a **controlled, evidence-gated proposal system** — not a runtime
mutator. It can propose and evaluate improvements, but it may **not** silently change
behavior, policies, memory rules, or permissions, and it never deploys itself.

## Engine (`metacognition.improvement.MetacognitionEngine`)
- Append-only, hash-chained proposal ledger (`verify_chain()`).
- Proposal kinds: `workflow`, `policy`, `permission`, `memory_rule`.
- Detection: `detect_repeated_failures` (groups failures by target, threshold), `detect_performance_drift`.
- Evaluation: `evaluate` compares a proposed policy against a baseline over historical +
  simulated cases via a pure `simulate` function; sets state to `evaluated`/`evaluated_failed`.
- Approval gate: `approve` enforces cross-actor, cross-role (SOD) and rejects proposals that
  failed evaluation or self/same-role approval.

## Deployment is explicit and gated (never automatic)
`apply_proposal` / `rollback_proposal` exist but are **never called by the engine**. A proposal
can only change runtime if a human explicitly calls them with an `APPROVED` proposal. This is
how the system "improves through evidence without silently taking control".

## Demonstrated in the restaurant pack
`RestaurantCapabilityPack.generate_metacognitive_proposal` builds a proposal from restaurant
outcomes, evaluates it deterministically, and records it as a governed `policy` record with
`applied=False` plus an evidence report. No proposal is deployed. The test asserts every policy
record has `applied=False`.

## What is NOT claimed
- No automated self-improvement in the pilot/capability runtime.
- Proposal deployment is a future, human-gated pipeline (see 12_roadmap.md).
