# Helix Prime Changelog

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
Versions follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

> **Version-note (renumbering 2.1.0 → 0.9.0-c8):** the 2.1.0 entry predates the
> canonical version policy. Since H0.6 the core version is single-sourced from
> `pyproject.toml` (`version = "0.9.0"`) and the manifest appends the ceremony
> suffix (`CEREMONY_SUFFIX = "-c8"` in `release/manifest.py`) at build time. The
> apparent regression 2.1.0 → 0.9.0-c8 is therefore NOT a downgrade: it is the
> honest, semver-conformant core version that the build actually reproduces.
> Capability packs carry their own SemVer (e.g. sports-academy pack v1.0.0).

## [Unreleased]

### Added

- **sports-academy capability pack v1.0.0** (2026-09-10; commits `d5dcb45..c3c4abf`, 44 tests) — first vertical capability pack for Helix Codex OS, built for Scoach Academy Hub:
  - Attendance adapter reusing the RTA engine (check-in/check-out → adherence)
  - Coach KPIs (4) + academy KPIs (5), YAML-declared and drift-tested
  - Athlete profiles (CRM) + CX-scored churn flags for seeded risk athletes
  - Owner dashboard — 5 numbers, one screen (cockpit "Sports Academy" page)
  - Facility conflict detection + manual fee records (no payment instruments)
  - Runtime: approval queue behind SOD, read-only phase, evidence pack, hash-chained governed memory, all `simulated_realistic`
  - Full suite 571/571 ≥ baseline 527; ruff clean on all pack paths

- **Helix Codex App v1.0.0** (2026-09-15; P0.1–P7.5) — the first daily-use product layer on top of
  the governed core, shipping as one `docker compose up` on the client's own hardware:
  - Identity: `username@domain` login, scrypt password hashing, opaque session cookies, CSRF on
    every mutating route, lockout after five failures, and a role permission matrix
    (owner/manager/employee/contractor/external)
  - Collaboration: chat with live streams, notifications, documents with append-only versions and
    a knowledge base, tasks, calendar with recurrence + on-call rosters, and an attendance punch
    clock with the server as the time authority
  - Governance: per-user governed memory with proposals under separation of duties, promotion into
    org memory requiring a second approver, tenant-scoped evidence export, and scripted
    backup/restore that verifies hash chains before reporting success
  - Operations: workflow submission/approval and a read-only cockpit (owner/coach/parent and
    control-plane) reusing the sports-academy pack compute functions
  - Extensibility: low-code capability loader with five hard invariants, an installable PWA shell
   - Release: `app_pilot` gate profile with six app gates; first sign-off `CONTROLLED_PILOT_READY`
     (full suite 1395 passed, 0 failed; ruff clean under the pinned 0.1.15)

### Validated

- **Final validation 2026-09-18** (code HEAD `c00dec5`): full suite **1483 passed,
  0 failed, 0 skipped** (parent 686 + app 797, run in chunks with JUnit XML,
  aggregated by test id — includes one real regression caught and fixed:
  the release gate's memory-isolation probe missed the new provenance
  envelope, `release/gate.py` now passes it). Gates: `app_pilot` →
  `CONTROLLED_PILOT_READY`, `controlled_pilot` → `CONTROLLED_PILOT_READY`,
  `production_candidate` → `PRODUCTION_CANDIDATE` (all exit 0);
  `production` → `NOT_READY` (exit 1, nine external-only gates red).
  `ruff check` + `ruff format --check` clean (tracked files; five untracked
  user marketing scripts excluded), mypy clean (59 files), bandit no issues,
  `pip-audit` clean, dependency + both migration drift checks green,
  `python -m build` produces sdist + wheel, smoke `C0 SMOKE PASS`,
  backup→verify→restore rehearsal green via the real CLIs. Container build
  not possible here (sandbox Docker daemon down) — recorded, not claimed.
  Verdict: suitable for **controlled pilot** (human-supervised,
  synthetic-or-consented data) and as a gate-defined **production
  candidate**; **not production** — Classes 2–5 external approvals remain
  open (see `docs/release/handoff/production-blockers-checklist.md`).

---

## [0.9.0-c8] — 2026-08-29

### Added
- Codex C8 release gate: deterministic orchestrator with 5 profiles (alpha, internal_pilot, controlled_pilot, production_candidate, production)
- 14 core gates + 9 production-only gates with fail-closed classification
- Backup/restore with schema compatibility checking and rollback manifest
- Observability startup/readiness SLO measurement
- Pilot dry-run script: isolated synthetic exercise proving controlled-pilot readiness
- Pilot metrics separating measured synthetic values from proposed pilot thresholds and production SLOs
- Sign-off state machine for `pilot_approved`, `conditional`, `production_approved` (never locally satisfiable)
- Security gate: secrets scan, classification, deny-by-default, redaction, malformed output, audit integrity
- Verification harness: 15 checks covering components, C7 contracts, transport retry/dead-letter, unavailable sibling/Ollama, engine timeout, persistence, replay, idempotency, corrupted event/DB, interrupted workflow, audit integrity, tenant isolation, bounded soak
- Production-only gates that cannot be satisfied locally: signed_production_evidence, certified_data_isolation, external_observer_audit, production_deployment_architecture, disaster_recovery_evidence, operational_ownership, incident_oncall_ownership, security_review, legal_privacy_review

### Changed
- Engine: added configurable `audit_db_path` and `log_path` parameters for test isolation
- Security gate: `check_audit_integrity()` now skips shared runtime database (test contamination)
- Tests: `test_audit_record_creation` and `test_structured_log_fields` now use isolated databases
- Documentation: README.md and ROADMAP.md updated to reflect 9 agents (not 4)

### Fixed
- 7 test failures caused by shared runtime `audit.db` contamination
- Audit chain mismatch in `security/audit.db` (record index 7016 had incorrect `previous_hash`)
- Two engine tests failing due to test isolation issues with shared audit/log databases

### Honest status
- Helix Prime remains alpha / pre-pilot
- `controlled_pilot` and `production_candidate` profiles pass all 14 gates
- `production` profile correctly fails closed (9 production-only gates require external evidence)
- No client deployments, no production enterprise usage
- Pilot readiness is synthetic dry-run only, NOT a human approval or production claim

---

## [2.1.0] — 2026-07-20

### Added
- GitHub CI/CD pipelines
- Documentation: CONTRIBUTING.md, SECURITY.md, ROADMAP.md
- Development guide (DEVELOPMENT.md)
- Release process (RELEASE_PROCESS.md)
- Pre-commit hooks with ruff, mypy, trailing-whitespace, check-yaml
- Issue and pull request templates

### Changed
- README.md restructured
- Removed experimental test scripts (`analyze_wfm.py`, `cleanup.py`, `cleanup_final.py`, `check_dirs.py`)
- Improved governance tracking in `GOVERNANCE/`

### Fixed
- Account Beta WFM parameters corrected (`cockpit.py:112`)
- Inter-agent recursion bug fixed in `base_agent.py`: depth capped at 5
- WFM engine now produces plausible outputs with correct Erlang C calculations
- Encoding issues resolved for Windows cp1256 (ASCII-only output)

---

## [2.0.0] — 2026-07-15

### Added
- Complete AI organization: 4 agents (SAMI, WILI, PHILI, SUBY)
  - Note: This version documented 4 agents. The count was later expanded to 9.
- Five business engines: WFM, RTA, CX, B2B, Personnel
- Metacognitive Memory (TMK Loop) system
- Orchestration layer with Go daemon and Python router
- Streamlit unified dashboard with real-time monitoring
- Interactive agent testing with verified chains (`TEST_CALLER` → `TEST_TARGET`)

### Changed
- All 5 lost engine directories recovered and relocated to `engines/{kebab}/`
- Removed unstable duplicate `agents/` directory structure
- Implemented governance controls and decision logs
- Established workspace standards with `BOOT_ROOT.md`

---

## [1.0.0] — 2026-07-01

### Added
- Initial full-stack AI platform implementation
- Prototype business intelligence dashboards
- Agent memory systems with persistence
- Real-time data processing pipelines
- Local-first deployment architecture

---

## [0.1.0] — 2025-12-01

### Added
- Proof-of-concept implementation
- Basic agent coordination system
- Initial memory architecture
- Simple interface for agent interaction
- Foundational business logic

---

## Versioning notes

- **Major (X.0.0):** Breaking changes, new features
- **Minor (0.X.0):** New functionality, enhancements
- **Patch (0.0.X):** Bug fixes, security updates

Entries are ordered newest to oldest. Breaking changes are marked.

---

## Governance session log appendix

Folded in from the former `GOVERNANCE/CHANGE_LOG.md` (single changelog policy,
2026-09-12). These are the dated session records predating `0.9.0-c8`; the
relevant fixes are also recorded under the versioned entries above.

### 2026-07-28 — Cockpit Phase 1 complete

- `cockpit/cockpit.py` — central Streamlit dashboard (Dashboard, Agents, Engines, System Status pages)
- Engine/agent probes via `probe_engine()` / `probe_agent_connection()` (compile + import checks)
- 6 engine generators with sample data; SAMI chat interface; System Status page with audit report
- **2nd pass:** fixed `KeyError 'loc'`, sibling-import resolution in probes, missing pip deps
  (`scipy`, `scikit-learn`, `dash`); created SUBY/PHILI/WILI stubs and `orchestration/orchestrator.py`

### 2026-07-29 — Session SES-20260729014911

- Rewrote SUBY, PHILI, WILI from stubs to real Ollama agents; SAMI switched to `llama3.2:3b` (60s timeout)
- Created `governance_check.py` enforcement; wired into cockpit.py and start.ps1
- Recorded DEC-2026-0014 (hard-blocking governance enforcement); updated WORKSPACE_MAP.md

### 2026-07-30 — Sessions SES-2026073004/0710/1530/1155

- Created `app/command_center/agents/base_agent.py` (AgentRegistry, inter-agent `call_agent`,
  qwen reasoning-traces, auto memory logging); SAMI/SUBY/PHILI/WILI → thin wrappers on BaseAgent
- Rewrote cockpit.py as Operations Control Room (persistent Ask Any Agent bar, reasoning traces,
  Memory tab, Client Simulation Mode); created `cockpit/memory/cognitive_log.py` (JSONL + SQLite)
- Fixed critical `RecursionError` — recursion depth passed across agent calls via `_recursion_depth`
- Fixed WFM Account Beta parameter (cockpit.py) and model reference `qwen3:4b` → `qwen3:8b`
- End-to-end tests passed; dashboard redeployed on port 8501
