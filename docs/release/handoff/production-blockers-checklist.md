# External Production Blockers — Verification Checklist

> **STATUS: STILL LIVE (re-verified 2026-09-18).** Scope line refreshed for the
> current build: Helix Prime Codex `0.9.0-c8` at HEAD `c00dec5`, full suite
> **1483 passed / 0 failed / 0 skipped** (JUnit XML per chunk, aggregated by
> test id; was 621 at the 2026-09-12 snapshot). Gates re-run the same day:
> `app_pilot` → `CONTROLLED_PILOT_READY`, `controlled_pilot` →
> `CONTROLLED_PILOT_READY`, `production_candidate` → `PRODUCTION_CANDIDATE`
> (all exit 0, zero red gates); `production` → `NOT_READY` (exit 1, all nine
> external-only gates red — correctly fails closed). All Class 2–5 items
> remain intentionally `OPEN`. The fail-closed statement below is unchanged
> and still binding.

Fail-closed: for the product to reach `PRODUCTION_READY`, **every** item below must be
independently satisfied. Any `NO`/blank answer keeps release `NOT_READY`. This checklist
separates who/what is responsible for each class of verification and is deliberately not
self-asserted. No value in this file is a substitute for real external evidence.

Scope: Helix Prime Codex `0.9.0-c8` at HEAD `c00dec5` (2026-09-18). The 2026-08-28
snapshot this checklist documents (307 tests, manifest `99f9bd37`,
`PRODUCTION_CANDIDATE`) is superseded on Class 1 rows only; Classes 2–5 are
version-independent external-evidence requirements and stay as written below.

---

## Class 1 — Verifiable by the coding agent (already demonstrated)

| # | Check | Gate | Status |
|---|-------|------|--------|
| 1.1 | Full regression suite passes | C0–C8 base | `PASS` (1483 passed, 0 failed, 2026-09-18) |
| 1.2 | Controlled-pilot release gate green | `controlled_pilot` | `PASS` (`CONTROLLED_PILOT_READY`) |
| 1.2b | App pilot release gate green | `app_pilot` | `PASS` (`CONTROLLED_PILOT_READY`) |
| 1.3 | Production release gate blocks release | `production` | `PASS` (`NOT_READY`, exit 1) — correctly fails closed |
| 1.4 | No `production_approved` fabricated | sign-off | `PASS` (False) |
| 1.5 | Synthetic/consented data boundary enforced | data gate | `PASS` |
| 1.6 | Evidence isolated + gitignored | evidence | `PASS` |
| 1.7 | Audit chain integrity verified | audit | `PASS` |
| 1.8 | Tenant isolation enforced (cross-tenant denied) | isolation | `PASS` |
| 1.9 | No secrets/DBs/logs/venvs tracked in git | scan | `PASS` |
| 1.10 | Backup/restore/rollback cycle green | backup/rollback | `PASS` |

These are **necessary but not sufficient** for production. They prove the local,
deterministic, synthetic pilot is under control — not production readiness.

## Class 2 — Verifiable by project owner / operator (human-decision items)

| # | Item | Required evidence | Status |
|---|------|-------------------|--------|
| 2.1 | Pilot operator named | Named human operator + rotation | `OPEN` |
| 2.2 | Pilot reviewer (SOD) named | Named independent human reviewer, distinct from operator | `OPEN` |
| 2.3 | Data controller named | Named human data controller + consent record | `OPEN` |
| 2.4 | Pilot go/no-go consent recorded | Human-approved go/no-go, not self-asserted | `OPEN` |
| 2.5 | Pilot success metrics gathered over a real runtime window | Metrics report + session log | `OPEN` |
| 2.6 | Pilot exit review recorded | Human exit review (does not imply prod readiness) | `OPEN` |

## Class 3 — Independent external reviewer (independent ownership)

| # | Item | Required evidence | Status |
|---|------|-------------------|--------|
| 3.1 | Independent external observer audit of the release pipeline | Third-party audit report | `OPEN` |
| 3.2 | Independent review of the controlled-pilot evidence pack | Reviewer report, signed | `OPEN` |
| 3.3 | Independent verification that pilot outputs are synthetic/consented only | Reviewer attestation | `OPEN` |

## Class 4 — Legal / privacy / security review

| # | Item | Required evidence | Status |
|---|------|-------------------|--------|
| 4.1 | Security review | Signed independent security review | `OPEN` |
| 4.2 | Legal / privacy review (incl. any personal or regulated data) | Signed legal/privacy review | `OPEN` |
| 4.3 | Certified tenant/data isolation | Independent certification of isolation guarantees | `OPEN` |
| 4.4 | Records/compliance review (ICT, financial, personnel prohibitions) | Legal sign-off that no prohibited category is touched | `OPEN` |

## Class 5 — Real infrastructure / deployment evidence

These cannot be produced by this coding agent; they require a real environment.

| # | Item | Required evidence | Status |
|---|------|-------------------|--------|
| 5.1 | Signed production deployment architecture | Approved topology + reviewer sign-off | `OPEN` |
| 5.2 | Disaster-recovery evidence in a real environment | Validated DR/backup run + recovery records | `OPEN` |
| 5.3 | Network sibling transport validated for production | Real-transport integration + load test evidence | `OPEN` |
| 5.4 | External IdP / cloud observability validated for production | Real integration evidence + credentials owner | `OPEN` |
| 5.5 | Operational ownership | Named production ops owner + rotation | `OPEN` |
| 5.6 | Incident / on-call ownership | Named production on-call + escalation | `OPEN` |
| 5.7 | Real production smoke/soak over a defined window | Execution log + metrics | `OPEN` |
| 5.8 | Production release sign-off | Human `production_approved` + signature reference | `OPEN` |

---

## Fail-closed statement

Production release `NOT_READY` because, at minimum, every Class 2–5 item above is `OPEN`
and unverified by an appropriate party. The product remains in a human-supervised
**controlled pilot** state with a synthetic/consented data boundary. Reaching production
requires genuine external evidence for Class 3, 4 and 5 items and real human decisions for
Class 2 items. **Nothing in this checklist is self-asserted.**

External owner / approval / signature / audit fields are intentionally left `OPEN` and must
be filled only by real humans or external parties — never fabricated.
