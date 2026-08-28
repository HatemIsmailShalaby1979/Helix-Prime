# Helix Prime Codex C8 — Production Blockers (9 Gates)

Status: these nine production-only gates are NOT satisfiable in a local/controlled
release. They are the hard blockers that prevent any bare `PRODUCTION` label in
C8. Machine mirror: `release/profiles.py` → `PRODUCTION_ONLY_GATES`.

The C8 gate (`release/gate.py`) returns `PRODUCTION` only if ALL NINE of these are
green AND a genuine human `production_approved` sign-off exists. Locally these
gates are fail-closed red, so the release can only ever emit `CONTROLLED_PILOT_READY`
or `PRODUCTION_CANDIDATE` — never `PRODUCTION`.

## The nine production-only gates

1. **`signed_production_evidence`** — evidence pack cryptographically signed by a
   key held outside the local environment. Not satisfiable locally.
2. **`certified_data_isolation`** — independent certification of tenant data
   isolation at production scale. Not satisfiable locally.
3. **`external_observer_audit`** — independent third-party audit of the control
   plane and audit chain. Not satisfiable locally.
4. **`production_deployment_architecture`** — approved production deployment
   topology (networking, TLS, HA, secrets management). Not satisfiable locally.
5. **`disaster_recovery_evidence`** — validated DR/backup plan for the production
   environment. Not satisfiable locally.
6. **`operational_ownership`** — named production operations owner and rotation.
   Not satisfiable locally.
7. **`incident_oncall_ownership`** — named production on-call and escalation
   contract. Not satisfiable locally.
8. **`security_review`** — completed independent security review/pen-test of the
   production release. Not satisfiable locally.
9. **`legal_privacy_review`** — completed legal and data-privacy review for the
   production jurisdiction. Not satisfiable locally.

## Consequence

Because blockers 1–9 are red by construction and no local `production_approved`
sign-off is obtainable, the C8 pipeline is fail-closed against production release.
This is deliberate: no controlled-pilot artefact may be mislabelled as production.

## Defeating a block is a defect

Any change that makes one of these gates green locally, or that fabricates a
`production_approved` sign-off, is a defect and must be rejected in review.
