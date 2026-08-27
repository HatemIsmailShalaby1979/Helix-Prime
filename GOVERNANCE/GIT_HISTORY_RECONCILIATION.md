# GIT History Reconciliation — Codex Phase C0

**Date:** 2026-08-27
**Commits observed:** 2

```
1411df94 Fix cockpit launch, add setup.bat, relax Python deps to 3.10+ (HEAD -> main, origin/main)
03185c6f Initial commit - Helix-Prime ready for GitHub
```

**Governance log claims:** `GOVERNANCE/CHANGE_LOG.md` records 7 sessions:

- 2026-07-28 — Cockpit Phase 1 Complete + 2nd pass (6 engines, 4 agents, orchestrator probe fix)
- 2026-07-29 — SES-20260729014911 (5 changes: generate.ts, SUBY/PHILI/WILI rewrite, SAMI model qwen3, etc.)
- 2026-07-30 — SES-20260730042635 (cognitive_log.py + BaseAgent inter-agent + cockpit Operations Control Room 6 pages)
- 2026-07-30 — SES-20260730071018 (model 4b->8b)
- 2026-07-30 — SES-20260730153000 (RecursionError fix, CHANGELOG/CURRENT_SPRINT)
- Additional session folders reference governance_check.py, .governance_state.json, audit-log/ground_truth_2026-07-30-04-22-53.md

## Truth statement

- The **2-commit** history is the only git-verifiable history. All intermediate governance-described changes arrived as **unverified imported work** directly into the working tree without commits (observed via `git diff` inclusion of `.venv` as tracked artifact creating noisy diff).
- No commit hash can be cited for intermediate sessions. The ground-truth audit log `GOVERNANCE/audit-log/ground_truth_2026-07-30-04-22-53.md` is preserved but its listing of `engines/(empty)` contradicts current `engines/` population (6 engines present). The audit log is therefore treated as a **point-in-time probe snapshot**, not a deployment claim.
- The capability matrix `GOVERNANCE/capability-matrix.json` (C0) is the new signed baseline replacing MASTER_STORY.md claims.

## Remediation chosen — Preserve history where possible, record imported work explicitly

- **Do NOT rewrite** `1411df9`/`03185c6` (public history). No `git push --force` without explicit owner approval.
- **Record imported/unverified work** in this file + `capability-matrix.json` known_gaps; treat pre-C0 changes as `imported` not `verified commits`.
- **Phase C0 commits** will be linear fast-forward from `1411df9` containing: `.gitignore` hygiene (untrack .venv), `pytest.ini` fix, `GOVERNANCE/capability-matrix.json`, `GOVERNANCE/RELEASE_LABELS.md`, `evidence/README.md`, `scripts/smoke.py`, and reconciling doc commits. No squash of `.venv` history — git's `rm --cached` preserves recoverability via prior commit; local `.venv` retained.
- **Future enforcement:** pre-commit hook `check-added-large-files` remains enabled; `.venv/` now git-ignored prevents recurrence.

## Recovery

To recover pre-C0 unverified file states, use working-tree copy vs. `git show HEAD:<path>`; do not assume commit history covers them. After C0 evidence pack is signed, tag `c0-baseline` without force-push.

## Sign-off

- [ ] 2026-08-27 Owner confirms above reconciliation and authorizes C0 hygiene commit.
