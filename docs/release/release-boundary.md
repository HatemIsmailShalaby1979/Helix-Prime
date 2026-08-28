# Helix Prime Codex C8 — Release Boundary and Profiles

Authoritative reference for the C8 release profiles and the boundary between a
controlled pilot / production candidate and a `PRODUCTION` release.

Machine-readable mirror: `release/release-profiles.yaml`
Gates backend: `release/profiles.py`

## Release profiles

| Profile | Meaning | C8 goal? |
|---------|---------|----------|
| `alpha` | development / exploration | no |
| `internal_pilot` | internal team only | no |
| `controlled_pilot` | human-supervised, synthetic/consented data | yes (goal) |
| `production_candidate` | evidence pack accepted, NOT released | yes (goal) |
| `production` | requires production-only gates NOT satisfied in C8 | NO |

## Gate set

14 gates: repository_state, reproducible_install, configuration_validation,
dependency_locking, startup_readiness, backup_restore, rollback, data_isolation,
audit_integrity, security_checks, failure_recovery, performance_limits,
operator_readiness, release_approval.

`controlled_pilot` and `production_candidate` require ALL 14.

## Production-only gates (never claimed in C8)

The nine production-only gates (see `production-blockers.md` and
`release/profiles.py` → `PRODUCTION_ONLY_GATES`) are fail-closed red locally:

1. `signed_production_evidence`
2. `certified_data_isolation`
3. `external_observer_audit`
4. `production_deployment_architecture`
5. `disaster_recovery_evidence`
6. `operational_ownership`
7. `incident_oncall_ownership`
8. `security_review`
9. `legal_privacy_review`

`PRODUCTION` is emitted only if ALL NINE are green AND a genuine human
`production_approved` sign-off exists. Because these are never satisfiable
locally, the C8 gate can only ever emit `CONTROLLED_PILOT_READY` or
`PRODUCTION_CANDIDATE` — never a bare `PRODUCTION` label.

## Classification

`release/gate.py` aggregates gate results and classifies fail-closed:
- all required gates green + requested profile `production_candidate`
  -> `PRODUCTION_CANDIDATE`
- all required gates green + requested profile `controlled_pilot`
  -> `CONTROLLED_PILOT_READY`
- any red gate -> `NOT_READY` (non-zero exit)

## Boundary / non-goals (from C8 ticket)

No customer deployment, no production client data, no cloud deployment, no
external IdP/monitoring, no network sibling transport, no new GM capabilities,
no new engine logic, no broad cockpit redesign, no autonomous irreversible
actions, no commercial/scalability claims, no L&D Command Center Windows build,
no force-push/remote publication.
