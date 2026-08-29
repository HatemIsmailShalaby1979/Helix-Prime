# Helix Prime Changelog

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
Versions follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
