# Helix Prime Codex C8 — Controlled Pilot Operating Protocol

Status: **controlled pilot** operating protocol. This defines HOW a human-supervised
pilot is run. It does NOT claim production readiness or unfettered autonomy.

Companion docs:
- Scope/data/consent boundaries: `controlled-pilot-pack.md`
- Operator steps: `operator-runbook.md`
- Incident handling: `incident-response.md`
- Backup/restore/rollback: `backup-restore-guide.md`
- Gate/profiles/boundary: `release-boundary.md`
- Go/no-go sign-off model: `signoff.md`
- Operational metrics: `metrics.md`

---

## 1. Scope and boundary

The controlled pilot exercises the real control plane, six engines, nine agents,
GM aliases, C7 sibling contracts, audit, classification, authorization,
persistence, and backup/restore — using **synthetic or explicitly consented
data only**.

Out of scope: customer deployment, production client data, cloud deployment,
external IdP, cloud observability, network sibling transport, autonomous
irreversible actions, commercial/scalability claims, L&D Command Center Windows
build, and any unauditable operator decision.

## 2. Pilot data and consent

- All input payloads MUST be `is_sample: true` (synthetic) or carry explicit
  consent evidence.
- The source of truth is `release/go-no-go.json`, whose `data_scope` is
  `SYNTHETIC_OR_CONSENTED_ONLY`.
- Using non-synthetic, non-consented data is prohibited at every step.
- No real secrets, tokens, or credentials are ever entered, logged, committed,
  or persisted during a dry-run.

## 3. Roles and responsibilities

| Role | Responsibility |
|------|----------------|
| Operator (pilot lead) | Runs the gate and dry-run, reviews evidence, owns the pilot. |
| Reviewer | Independently reviews the evidence pack and sign-off conditions. |
| Data controller | Confirms data is synthetic or consented; nothing else. |
| Sibling service proxy | Runs deterministic fake siblings over in-memory transport only. |

No single role may both run the gate and unilaterally approve the sign-off.

## 4. Preconditions (go prerequisites)

Before any pilot run:
1. Working tree is clean and reproducible (`reproducible_install` green).
2. Configuration validated; no real endpoints configured for siblings.
3. Security gate passes (secrets, classification, deny-by-default, redaction,
   malformed-output, audit-integrity).
4. A fresh isolated state directory is allocated for the run.
5. Evidence directory is writable under `evidence/pilot/<timestamp>/`.

## 5. Gate and dry-run procedure

Run, in order:
```
python3 scripts/release_gate.py --profile controlled_pilot
python3 scripts/pilot_dry_run.py
```
- The gate must emit `CONTROLLED_PILOT_READY`, never a bare `PRODUCTION` label.
- The dry-run must report `CONTROLLED_PILOT_READY` and exit 0 with all checks
  green.
- If either is red, record the block and do not proceed to sign-off.

## 6. Sign-off workflow (go/no-go)

See `signoff.md` for the state machine and `release/go-no-go.json` for the file.
- An `internal_review` or `pilot_approved` sign-off is LOCAL consent, never a
  fabricated human acceptance and never a `production_approved` proof.
- `production_approved` is NOT satisfiable locally (fail-closed).
- `conditional` sign-offs require every recorded condition to be satisfied.
- Expired sign-offs are rejected.

## 7. Operational limits and guardrails

- No autonomous irreversible actions; every impactful decision requires an
  explicit allow.
- SAMI-approval gate is mandatory for the vertical slice.
- Engine work is deadline-enforced; timeouts are captured, not hidden.
- Siblings run over in-process/in-memory transport only — no network.

## 8. Monitoring and metrics

See `metrics.md` and `release/pilot_metrics.py`.
- Measured values come only from the SYNTHETIC dry-run.
- Proposed pilot thresholds and production SLOs are explicitly NOT validated
  or claimed.

## 9. Escalation and incidents

Follow `incident-response.md`: severity definitions, per-incident runbooks
(store unavailable, audit tamper, engine timeout/dead-letter, sibling
unavailable, corrupted event), and an escalation path. Any unresolved incident
blocks the pilot.

## 10. Evidence and auditability

- Each run writes an evidence pack under `evidence/pilot/<timestamp>/`
  (gitignored, not committed).
- The audit chain must verify after every run (`audit_verification_rate`).
- Never fabricate evidence; record only what the dry-run actually produced.

## 11. Backup, restore, and rollback

Use `backup-restore-guide.md`. Every pilot run proves backup + restore on its
isolated state and confirms the restored audit chain verifies. Rollback restores
the previous committed manifest, never the live database.

## 12. Security and data-private checks

`security_gate.run_security_gate` runs on every dry-run: secrets scan, data
classification, deny-by-default, redaction, malformed-output, and audit
integrity. Any violation fails the run closed.

## 13. Non-goals and prohibitions

Re-stated from `release-boundary.md`: no production deployment, no real data, no
network siblings, no autonomous irreversible actions, no commercial claims, no
force-push, no remote publication of the pilot state.

## 14. Pilot schedule and exit criteria

A pilot run is bounded (per-session, per-evidence-pack) and reproducible. Exit
criteria to conclude or graduate:
- `CONTROLLED_PILOT_READY` + all dry-run checks green for the session, AND
- reviewer review recorded, AND
- every `conditional` condition closed, AND
- documented operational metrics gathered.

Exit does NOT imply `PRODUCTION_READY`; graduating to production requires the
production-only gates plus a genuine human `production_approved` sign-off, which
the local system cannot fabricate.

## 15. Approval and sign-off record

The end of a pilot records the go/no-go decision in `release/go-no-go.json` with
approver identity, role, decision, timestamp, and evidence refs. This record is
local consent (or a clear non-approval). It is the input to a separate human
process for any broader rollout — it is never, by itself, a production release.
