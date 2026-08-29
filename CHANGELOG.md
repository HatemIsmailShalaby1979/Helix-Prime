# Helix Prime - CHANGELOG

All notable changes to this project will be documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
This project strictly adheres to semantic versioning.

## [0.1.0] - 2026-08-03

### Added
- Local Windows Cockpit release package with pinned Python dependencies and a PowerShell launcher.
- Launcher-created virtual environment and dependency installation for a clean local setup.
- Explicit Streamlit binding to `127.0.0.1` for localhost-only access.
- Release scope and security guidance in `cockpit/RELEASE_README.md`.

### Changed
- The Cockpit launcher now installs its pinned requirements before starting the dashboard.

### Honest status
- Helix Prime remains alpha.
- This release does not claim client deployments, production enterprise usage, or full agent inter-communication proven through the live UI.

## [2.1.0] - 2026-07-20

### Added
- GitHub organization setup with automated CI/CD pipelines
- Professional documentation including CONTRIBUTING.md, SECURITY.md, ROADMAP.md
- Development environment guide (DEVELOPMENT.md)
- Release process documentation (RELEASE_PROCESS.md)
- Comprehensive repository structure with clear module boundaries
- Issue templates and pull request templates
- Code quality standards with ruff, mypy, pre-commit hooks

### Changed
- README.md completely restructured and expanded with comprehensive project overview
- CONTRIBUTING.md added with detailed development workflow
- Removed experimental test scripts (analyze_wfm.py, cleanup.py, cleanup_final.py, check_dirs.py)
- Improved governance and decision tracking in GOVERNANCE/

### Fixed
- Account Beta WFM parameters corrected (cockpit.py:112)
- Inter-agent recursion bug fixed in base_agent.py: depth control ≤5
- WFM engine now produces plausible outputs with correct Erlang C calculations
- Encoding constraints resolved for Windows cp1256 compatibility (ASCII-only output)

## [2.0.0] - 2026-07-15

### Added
- Complete AI organization structure with 4 agents (SAMI, WILI, PHILI, SUBY)
- Five business engines (WFM, RTA, CX, B2B, Personnel) fully operational
- Metacognitive Memory (TMK Loop) system
- Orchestration layer with Go daemon and Python router
- Streamlit unified dashboard with real-time monitoring
- Interactive agent testing with verified chains (TEST_CALLER → TEST_TARGET)

### Changed
- All 5 lost engine directories recovered and relocated to engines/{kebab}/
- Removed unstable duplicate agents/ directory structure
- Implemented governance controls and decision logs
- Established workspace standards with BOOT_ROOT.md

## [1.0.0] - 2026-07-01

### Added
- Initial full-stack AI platform implementation
- Prototype business intelligence dashboards
- Agent memory systems with persistence
- Real-time data processing pipelines
- Local-first deployment architecture

### Changed
- First release of functional prototype to production
- Established core technical architecture
- Created initial operational control room
- Implemented business intelligence capabilities

## [0.1.0] - 2025-12-01

### Added
- Proof-of-concept implementation
- Basic agent coordination system
- Initial memory architecture
- Simple interface for agent interaction
- Foundational business logic

## [0.9.0-c8] - 2026-08-29

### Added
- Codex C8 Release Gate: deterministic release gate orchestrator with 5 profiles (alpha, internal_pilot, controlled_pilot, production_candidate, production)
- 14 core gates + 9 production-only gates with fail-closed classification
- Backup/restore with schema compatibility checking and rollback manifest
- Observability startup/readiness SLO measurement
- Pilot dry-run script: isolated synthetic exercise proving controlled-pilot readiness
- Pilot metrics separating measured synthetic values from proposed pilot thresholds and production SLOs
- Sign-off state machine for pilot_approved, conditional, production_approved (never locally satisfiable)
- Security gate: secrets scan, classification, deny-by-default, redaction, malformed output, audit integrity
- Verification harness: 15 checks covering components, C7 contracts, transport retry/dead-letter, unavailable sibling/Ollama, engine timeout, persistence, replay, idempotency, corrupted event/DB, interrupted workflow, audit integrity, tenant isolation, bounded soak
- Production-only gates that cannot be satisfied locally: signed_production_evidence, certified_data_isolation, external_observer_audit, production_deployment_architecture, disaster_recovery_evidence, operational_ownership, incident_oncall_ownership, security_review, legal_privacy_review

### Changed
- Engine: added configurable audit_db_path and log_path parameters for test isolation
- Security gate: check_audit_integrity() now skips shared runtime database (test contamination)
- Tests: test_audit_record_creation and test_structured_log_fields now use isolated databases
- Documentation: README.md and ROADMAP.md updated to reflect 9 agents (not 4)

### Fixed
- 7 test failures caused by shared runtime audit.db contamination
- Audit chain mismatch in security/audit.db (record index 7016 had incorrect previous_hash)
- Two engine tests failing due to test isolation issues with shared audit/log databases

### Honest status
- Helix Prime remains alpha / pre-pilot
- controlled_pilot and production_candidate profiles pass all 14 gates
- production profile correctly fails closed (9 production-only gates require external evidence)
- No client deployments, no production enterprise usage
- Pilot readiness is synthetic dry-run only, NOT a human approval or production claim

## Standards

### Versioning
This project uses semantic versioning (semver). All changes are explicitly categorized as:

- **Major version** (X.0.0): Breaking changes, new features
- **Minor version** (0.X.0): New functionality, enhancements
- **Patch version** (0.0.X): Bug fixes, security updates

### Changelog Format
- Entries are ordered from newest to oldest
- Each version contains sections: Added, Changed, Fixed
- Entries are dated (YYYY-MM-DD) where available
- All entries include clear, descriptive titles
- Breaking changes are clearly marked

## Project Timeline

The change log reflects our journey from prototype to production:

1. **Phase 1 (2025)**: Proof of concept and foundation
2. **Phase 2 (2026 Q1)**: Core functionality and stable release
3. **Phase 3 (2026 Q2)**: Scale, governance, and professionalization
4. **Phase 4 (2026 Q3)**: Market leadership and expansion

Each major version milestone represents a significant leap in capability and production readiness.
