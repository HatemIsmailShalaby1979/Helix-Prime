# Final Validation Report — Self-Hosted Production Candidate (2026-09-18)

Code HEAD validated: `c00dec5`. This report lands with the ledger/docs
commit on top; `git log --oneline -3` shows the exact validation commit.
No production readiness is claimed. Push/tag commands are deliberately
absent — they are issued only after the human owner reviews this report.

## Exact test counts

Full suite run in chunks with `--junitxml`, aggregated by test id
(artifacts kept outside the repo, not committed):

| Chunk | Tests | Failed |
|---|---|---|
| Parent P1 (contracts, control plane, connectors, policy, readiness dry-runs) | 312 | 0 |
| Parent P2 (engines, agents, server, security, new observability/scope/stream) | 224 | 0 |
| Parent P3 (vertical slice, release gate, pilot, packs, command center) | 139 | 0 |
| Parent P4 (server spine) | 11 | 0 |
| App A1 (accounts, admin, drift, packaging, gates, attendance) | 153 | 0¹ |
| App A2–A7 (all remaining app modules) | 644 | 0 |
| **Total unique** | **1483** | **0 (0 skipped)** |

¹ A1 first ran 152 passed / 1 failed: the release gate's
`app_memory_store_isolation` probe wrote a memory record without the new
provenance envelope and was correctly refused. Fixed in `release/gate.py`
(probe now passes the envelope); re-ran green. This is the validation
doing its job, not a waiver.

## Exact gate classifications (all `write_evidence=False`, tracked manifest untouched)

| Profile | Classification | Exit | Red gates |
|---|---|---|---|
| `app_pilot` | `CONTROLLED_PILOT_READY` | 0 | none |
| `controlled_pilot` | `CONTROLLED_PILOT_READY` | 0 | none |
| `production_candidate` | `PRODUCTION_CANDIDATE` | 0 | none |
| `production` | `NOT_READY` | 1 | all 9 external-only gates (signed evidence, certified isolation, observer audit, deployment architecture, DR evidence, ops ownership, on-call ownership, security review, legal/privacy review) |

## Static checks, audits, builds

- `ruff check` (CI scope): clean. `ruff format --check .`: clean on all
  tracked files (five untracked user marketing scripts excluded, untouched).
- `mypy server/ connectors/ control_plane/`: clean, 59 files.
- `bandit` (CI scope): no issues identified. `pip-audit` on the lock:
  no known vulnerabilities.
- `check_dependencies.py`: no drift. Migration drift (core 19/19,
  app 61/61): no drift.
- `python -m build`: sdist + wheel produced.
- `scripts/smoke.py`: `C0 SMOKE PASS` (engines 6/6, agents 4/4; its
  internal 30 s pytest probe times out by design — the full suite ran
  separately above).
- Container build: **not performed** — the sandbox Docker daemon is down
  (`docker info` hangs). Recorded honestly; the Dockerfile/compose surface
  is covered by 32 static packaging tests instead.
- Backup/restore rehearsal via the real CLIs on synthetic data:
  bootstrap → backup (3 captured) → `--verify-only` clean → restore to a
  clean target verified → prune dry-run safe.

## Git status at validation

Only `M marketing/README.md` (user-authored, preserved, never staged).
No secrets, `.db` files, or evidence directories staged or committed;
JUnit XML and build/rehearsal artifacts live outside the repo.

## Known residual risks

1. The full suite never ran as one process here (sandbox 10-minute
   command cap); chunked runs with per-test isolation are the evidence,
   and shared-process flakiness cannot be ruled out from these runs alone.
2. Container image unbuilt (daemon down) — first real `docker build` may
   surface issues the static tests cannot see.
3. Two sandbox-environment failures recorded historically (§1A) did not
   recur in this run; they remain environment-specific, not repo defects.
4. The release-gate probe fix (`release/gate.py`) is included in this
   validation commit — reviewed as a one-line envelope addition.

## External approvals still required (Classes 2–5, all OPEN)

Named pilot operator + reviewer (SOD), data controller, go/no-go consent,
pilot metrics window, exit review; independent observer audit and evidence
review; security, legal/privacy, certified isolation, records reviews;
production deployment architecture, DR evidence, transport/IdP validation,
ops/on-call ownership, production smoke/soak, production sign-off. See
`production-blockers-checklist.md`.

## Suitability verdict

- **Controlled pilot: SUITABLE** — human-supervised, synthetic-or-consented
  data only, with the runbook, rehearsal checklist, and monitoring alerts
  in place.
- **Production candidate: PERMITTED AS A GATE LABEL ONLY**
  (`PRODUCTION_CANDIDATE` emitted by the gate) — this is a classification,
  not a readiness claim.
- **Production: NOT SUITABLE** — the `production` profile is `NOT_READY`
  and every Class 2–5 item is open. Nothing in this report authorizes
  production use.
