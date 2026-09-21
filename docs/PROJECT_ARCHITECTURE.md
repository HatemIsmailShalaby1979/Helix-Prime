# Helix Prime — Project Architecture Document

> **Authority chain:** `00_CONSTITUTION.md` → `docs/HELIX_CODEX_OS_MASTER_BLUEPRINT.md` → implementation
>
> **Status:** CONTROLLED_PILOT_READY (not production — 9 gates require external evidence)
>
> **Last verified:** 2026-09-20 — full suite: **1,758 passed, 0 failed, 0 skipped, in one uninterrupted process**
>
> **Commit:** `003709b`

---

## Table of Contents

1. [Repository Overview](#1-repository-overview)
2. [Directory Structure](#2-directory-structure)
3. [Core Architecture](#3-core-architecture)
4. [Package Documentation](#4-package-documentation)
5. [Key Files Reference](#5-key-files-reference)
6. [Production Readiness](#6-production-readiness)
7. [Security and Hygiene](#7-security-and-hygiene)
8. [Workflow and CI/CD](#8-workflow-and-cicd)
9. [Testing](#9-testing)
10. [Documentation Landscape](#10-documentation-landscape)
11. [Governance](#11-governance)
12. [Deployment](#12-deployment)
13. [Appendix](#13-appendix)

---

## 1. Repository Overview

**Helix Prime** (commercial name: **Helix Codex OS**) is a self-hosted AI operations platform. It is a governed, multi-tenant system that orchestrates AI agents (called "functional agents" or "GMs") through deterministic engines to perform enterprise operations — workforce management, real-time adherence, customer experience scoring, B2B onboarding, personnel/hiring, and CRM operations — all under a strict governance envelope that includes segregation of duties, financial approval limits, data classification, audit-chain integrity, and kill-switch emergency stops.

### Key Facts

| Property | Value |
|---|---|
| Repository | `https://github.com/HatemIsmailShalaby1979/Helix-Prime.git` (private) |
| Branch | `main` (`origin/main` is `b9d8fb6`; the unpushed backlog is measured with `git rev-list --count origin/main..HEAD`) |
| Python | 3.12 (requires `>=3.12,<3.13`) |
| Package version | `0.9.0` (single-sourced from `pyproject.toml`) |
| License | MIT |
| Backend | FastAPI (canonical artifact: `helix-api`) |
| Dashboard | Streamlit (secondary: `helix-cockpit`) |
| Database | SQLite (workflow store, app store, audit trail) |
| Governance | 23 release gates (14 C8 + app gates + 9 production-only) |
| Test count | 1,758 collected, all passing |

### Design Principles (from `00_CONSTITUTION.md`)

1. **Identity precedes implementation** — every capability must answer "why does it exist?"
2. **Truth is paramount** — `MASTER_STORY.md` records verified reality; `README.md`/`ROADMAP.md` are subordinate
3. **Architecture expresses truth** — the blueprint governs structure
4. **Discussions becoming documents** — any lasting discussion that generates knowledge becomes a document
5. **Self-improvement is a proposal** — until isolated evaluation, peer review, approval, versioning, and rollback exist

---

## 2. Directory Structure

```
E:\Helix-Prime\
│
├── 00_CONSTITUTION.md           # Supreme authority document (34 lines)
├── AGENTS.md                    # Build ledger — operational handoff (4,500+ lines)
├── README.md                    # Main facing document (170 lines)
├── pyproject.toml               # Single source of truth: packaging + tooling (271 lines)
├── requirements.txt             # Canonical runtime dependencies (55 lines)
├── requirements-dev.txt         # Dev/test tooling (24 lines)
├── CHANGELOG.md                 # Keep-a-Changelog (203 lines)
├── ROADMAP.md                   # Honest roadmap (104 lines)
├── DEVELOPMENT.md               # Development guide (105 lines)
├── SECURITY.md                  # Security policy (157 lines)
├── CODE_OF_CONDUCT.md           # Contributor Covenant v2.1 (33 lines)
├── CONTRIBUTING.md              # Contribution guide (113 lines)
├── LICENSE.md                   # MIT (9 lines)
├── MANIFEST.in                  # sdist inclusion rules (9 lines)
├── MASTER_STORY.md              # Verified reality record (~700 lines)
├── RELEASE_PROCESS.md           # Release process (266 lines)
├── desktop.py                   # Legacy desktop launcher (96 lines)
├── launch.py                    # Unified launcher: Streamlit cockpit (117 lines)
├── launch.bat                   # Windows launcher (17 lines)
├── run_tests.ps1                # Cross-platform test runner (14 lines)
├── setup.bat                    # Windows setup (44 lines)
├── setup.sh                     # Linux/macOS setup (45 lines)
│
├── .github/
│   ├── dependabot.yml           # Weekly pip + github-actions updates (31 lines)
│   └── workflows/
│       ├── ci.yml               # Main CI pipeline (88 lines)
│       └── python-publish.yml   # PyPI artifact build (24 lines)
│
├── .pre-commit-config.yaml      # Ruff + trailing-whitespace etc. (18 lines)
│
├── server/                      # FastAPI backend spine (helix-api) — 1,522 lines
│   ├── app.py                   # Application factory
│   ├── auth.py                  # Bearer-token authentication
│   ├── cli.py                   # Canonical entry point (helix-api)
│   ├── config.py                # Runtime configuration
│   ├── deps.py                  # Lifetime-scoped dependencies
│   ├── errors.py                # Typed application errors
│   ├── scope.py                 # API tenant-scope enforcement
│   ├── sse.py                   # Server-sent events
│   ├── models/
│   │   ├── node.py              # Unifying Node model
│   │   └── store.py             # Node storage
│   ├── features/
│   │   ├── health/router.py     # Liveness + readiness
│   │   ├── halt/router.py       # Kill switch HTTP
│   │   ├── chat/router.py       # Chat + SSE streaming
│   │   ├── stream/router.py     # SSE stream for workflow runs
│   │   ├── console/router.py    # Operator console
│   │   ├── docs/router.py       # Documents API
│   │   ├── tasks/router.py      # Tasks API
│   │   ├── workflows/           # Workflows HTTP + service + repo + schemas
│   │   ├── approvals/           # Approval queue HTTP
│   │   └── metrics/router.py    # Prometheus /metrics
│   └── templates/
│
├── control_plane/               # Governance control plane — 5,216 lines
│   ├── engine.py                # Execution engine (submit/approve/execute/cancel/rollback)
│   ├── governance.py            # Governance framework (RoleSpec, evaluate_gate, drift)
│   ├── store.py                 # Durable SQLite store
│   ├── workflow.py              # Workflow state machine
│   ├── events.py                # Event envelope
│   ├── kill_switch.py           # Emergency stop
│   ├── ports.py                 # Engine port protocol
│   ├── control_seam.py          # C5 contact-centre control seam
│   ├── vertical_slice/          # C5 vertical slice orchestration
│   └── schemas/sibling_events/  # C7 sibling-project integration
│
├── contracts/                   # Typed agent contracts — 2,015 lines
│   ├── task.py                  # Core contracts (TaskRequest, TaskResult, etc.)
│   ├── adapter.py               # C1→C2 compatibility seam
│   ├── segregation_of_duties.py # Single SOD implementation
│   ├── vocabulary.py            # Data-mode + classification vocabularies
│   ├── toolcall.py              # Structured tool call contracts
│   └── capabilities.yaml        # Generated mirror
│
├── security/                    # Security module — 1,230 lines
│   ├── audit.py                 # Tamper-evident audit trail
│   ├── classification.py        # Data classification (6 labels)
│   ├── identity.py              # Identity model
│   ├── policy.py                # Authorization policy seam
│   ├── secrets.py               # Secrets safety
│   └── injection.py             # Prompt/tool injection detection
│
├── organization/                # Organization/roles — 1,436 lines
│   ├── role_catalog.py          # Role catalog loader
│   ├── capability_registry.py   # Capability registry
│   ├── gm_activation.py         # GM activation
│   ├── role-catalog.yaml        # Canonical role catalog (9 agents)
│   └── capability-registry.yaml # Canonical capability registry (22 capabilities)
│
├── engines/                     # All engines — 6,522 lines
│   ├── contracts.py             # Engine adapter contract
│   ├── registry.py              # Engine registry
│   ├── b2b/                     # B2B onboarding (1,222 lines)
│   ├── crm/                     # CRM (1,166 lines)
│   ├── cx/                      # CX churn sentinel (1,887 lines)
│   ├── personnel/               # Personnel (2,130 lines)
│   ├── rta/                     # RTA command center (828 lines)
│   └── wfm/                     # WFM forecasting (2,068 lines)
│
├── connectors/                  # Provider-neutral connectors — 1,079 lines
│   ├── base.py                  # BaseConnector class
│   ├── contracts.py             # Connector contracts
│   ├── policy.py                # Write governance policy
│   ├── ports.py                 # Connector port protocol
│   ├── registry.py              # Connector registry
│   ├── fakes.py                 # Fake connectors (Salesforce, Zendesk, Clay)
│   └── gateway.py               # ConnectorGateway
│
├── helix_codex_app/             # App layer (daily-use product) — ~9,000 lines
│   ├── app.py, cli.py, config.py, db.py, deps.py, errors.py, templating.py
│   ├── integration/             # Parent-importing seam (8 modules)
│   ├── security/                # App identity & permission layer (7 modules)
│   ├── modules/                 # Feature modules (14 modules × repo/service/router)
│   │   ├── admin/               # Admin panel
│   │   ├── attendance/          # Punch clock
│   │   ├── calendar/            # Events + on-call
│   │   ├── cockpit/             # Dashboard views
│   │   ├── docs/                # Documents + editor
│   │   ├── identity/            # Auth (login/logout/password)
│   │   ├── lowcode/             # Pack loader
│   │   ├── memory/              # Proposals lifecycle
│   │   ├── messaging/           # Chat (SSE + cursor paging)
│   │   ├── notifications/       # Notifications + badge
│   │   ├── ops/                 # Ops overview + workflow governance
│   │   └── tasks/               # Task board
│   ├── templates/               # 30+ Jinja2 templates
│   └── static/                  # CSS, JS, fonts, icons, PWA, SW, vendor
│
├── cockpit/                     # Streamlit dashboard (secondary) — 1,029+ lines
│   ├── cockpit.py               # Legacy operations control room
│   ├── codex_command_center.py  # Codex command center
│   ├── command_center_integration.py  # Pure assembly (no Streamlit)
│   └── cli.py                   # Console entry point
│
├── memory/                      # Governed memory — 567 lines
│   └── governed_memory.py       # Append-only, hash-chained, tenant-isolated
│
├── metacognition/               # Improvement proposals — 494 lines
│   └── improvement.py           # Proposal lifecycle with hash-chained ledger
│
├── observability/               # Observability — 911 lines
│   ├── health.py                # Health/readiness checks
│   ├── logging.py               # Structured JSON logging
│   └── metrics.py               # Stdlib-only Prometheus registry
│
├── pilot/                       # Controlled pilot engine — ~1,600 lines
│   ├── run.py                   # Pilot runtime
│   ├── approval.py              # Approval records
│   ├── config.py                # Pilot config
│   ├── consent.py               # Consent records
│   ├── evidence_pack.py         # Evidence pack assembly
│   ├── metrics.py               # Pilot success metrics
│   ├── phases.py                # Read-only phases + connector permissions
│   └── scope.py                 # Pilot scope, policies, data modes
│
├── customer_success/            # Account health wedge — ~933 lines
│   ├── wedge.py                 # Main wedge: diagnose → approve → record
│   ├── health.py                # Health scoring
│   └── fixtures.py              # Deterministic fixtures
│
├── capabilities/                # Capability packs
│   ├── restaurant/              # Reference pack (pattern to copy from)
│   └── sports_academy/          # Scoach Academy Hub pack (built S0-S7)
│
├── release/                     # Release/gating system — 17 files, ~3,200 lines
│   ├── gate.py                  # Core release gate (23 gates)
│   ├── harness.py               # Gate harness
│   ├── profiles.py              # Gate profiles (derived from YAML)
│   ├── production_evidence.py   # Evidence verifier (RSA-PKCS#1)
│   ├── signoff.py               # Sign-off serialization + validation
│   ├── backup.py                # Backup logic
│   ├── observability.py         # Observability gate
│   ├── security_gate.py         # Security gate
│   ├── manifest.py              # Manifest generation
│   ├── pilot_metrics.py         # Pilot metrics
│   ├── release-profiles.yaml    # Source of truth for gate profiles
│   ├── release-manifest.json    # Last manifest (deliberately stale)
│   ├── go-no-go.json            # Pilot consent flag
│   └── manifest.schema.json     # Manifest schema
│
├── scripts/                     # Scripts — 14 files, ~1,800 lines
│   ├── check_governance_drift.py    # Governance drift checker
│   ├── check_migration_drift.py     # Alembic drift checker
│   ├── sync_capability_mirrors.py   # Mirror sync (CI: --check)
│   ├── export_evidence_pack.py      # Evidence exporter
│   ├── produce_production_evidence.py  # Evidence producer (gates/init-key/template/check/sign/status)
│   ├── record_production_signoff.py   # Sign-off recorder
│   ├── kill_switch.py             # Kill switch CLI
│   ├── smoke.py                   # Smoke test runner
│   ├── pilot_dry_run.py           # Pilot dry run
│   └── ...
│
├── tests/                       # Test directory — ~62 root files, ~42K lines
│   ├── conftest.py              # Shared fixtures
│   ├── test_c1_contracts.py     # C1 contract compliance (1,278 lines)
│   ├── test_c2_control_plane.py # Control plane (911 lines)
│   ├── test_c3_security.py      # Security (712 lines)
│   ├── test_c4_engines.py       # Engine productization (943 lines)
│   ├── test_c5_vertical_slice.py# Vertical slice (645 lines)
│   ├── test_c6_gm_expansion.py  # GM expansion (558 lines)
│   ├── test_c7_sibling_integration.py # Sibling integration (556 lines)
│   ├── test_c8_release_gate.py  # Release gates (575 lines)
│   ├── test_c8_gate_falsifiability.py # Falsifiability proofs (393 lines, 35 tests)
│   ├── test_segregation_of_duties.py  # SOD delegation proofs (776 lines, 70 tests)
│   ├── test_production_evidence.py    # Evidence verification (279 lines, 27 tests)
│   ├── test_vocabulary.py       # Vocabulary single-sourcing (45 tests)
│   ├── ... (40 more files)
│
├── docs/                        # Documentation — ~80 files, ~60K lines
│   ├── HELIX_CODED_OS_MASTER_BLUEPRINT.md  # Architecture + commercial record (522 lines)
│   ├── C3-threat-model.md       # Threat model (13 threats)
│   ├── sccoach_academy_hub_opportunity_report.md  # Business case (502 lines)
│   ├── sports_academy_pack.md   # Pack scope + governance
│   ├── architecture/            # Architecture overview + repo graph
│   ├── archive/                 # Superseded documents (SUPERSEDED banners)
│   ├── audits/                  # Audit plans and re-evaluations
│   ├── handoff/                 # Visual handoff dashboards + specs
│   ├── operations/              # Data retention, runbooks
│   ├── portfolio/               # Strategic docs (17 files)
│   └── release/                 # Release & deployment docs (18 files)
│
├── GOVERNANCE/                  # Governance — 22 files, ~1,600 lines
│   ├── IMPLEMENTATION_MATRIX.md # C1-C8 gate implementation matrix (545 lines)
│   ├── WORKSPACE_MAP.md         # Workspace map
│   ├── governance_check.py      # Governance check script (87 lines)
│   └── wayfinder/tickets/       # C0-C8 tickets
│
├── infra/                       # Infrastructure
│   ├── docker/                  # Dockerfiles + compose (5 files)
│   └── monitoring/              # Alerts + README (2 files)
│
├── integrations/                # External integrations — 8 files, ~1,900 lines
│
├── cloud/                       # Cloud code — 7 files, ~570 lines
│
├── orchestration/               # Orchestration — 3 files, ~365 lines
│
└── src-tauri/                   # Tauri desktop app (icon only)
```

---

## 3. Core Architecture

### 3.1 Architecture Layers

```
┌─────────────────────────────────────────────────────────────────┐
│                    helix_codex_app/                              │
│  (FastAPI + HTMX + Jinja2 — daily-use product layer)            │
│  Only imports parent core through integration/ seam             │
├─────────────────────────────────────────────────────────────────┤
│                    server/                                       │
│  (FastAPI spine — canonical artifact: helix-api)                │
│  Auth, features, middleware, all routes behind current_identity   │
├─────────────────────────────────────────────────────────────────┤
│                    control_plane/                                │
│  (Governance control plane — engine, store, governance, events) │
│  Engine: submit/approve/execute/cancel/rollback                  │
├──────────────┬──────────┬───────────┬───────────┬───────────────┤
│   security/  │ contracts│ engines/  │connectors │  organization │
│  (auth,      │ (typed   │ (6        │(provider- │  (roles +     │
│   audit,     │  agent   │  determin-│  neutral  │  capability   │
│   policy,    │  contracts│ istic    │  reads)   │  registry)    │
│   secrets,   │          │  engines) │           │               │
│   injection) │          │          │           │               │
├──────────────┴──────────┴───────────┴───────────┴───────────────┤
│                    memory/ (governed memory)                     │
│  Append-only, hash-chained, tenant-isolated, classification-aware│
├─────────────────────────────────────────────────────────────────┤
│                    observability/ (metrics + logging + health)    │
│                    metacognition/ (improvement proposals)         │
│                    pilot/ (controlled pilot orchestration)        │
│                    customer_success/ (account health wedge)       │
└─────────────────────────────────────────────────────────────────┘
```

### 3.2 The Eight Gates (C0-C8)

| Gate | Description | Status |
|------|-------------|--------|
| **C0** | Collide & Cleanup | Complete. Single source of truth for versions/configs, no duplication |
| **C1** | Organization + Contracts | Complete. Role catalog = single source, contracts typed, SOD unified |
| **C1a** | Capability Discovery | Complete. Registry loads canonical YAML directly |
| **C2** | Control Plane | Complete. Engine with state machine, governance enforcement |
| **C3** | Security + Observability | Complete. Audit trail, classification, injection, metrics, logging |
| **C4** | Engine Productization | Complete. 6 deterministic engines with adapters |
| **C5** | Vertical Slice | Complete. 9-step chain from data to SAMI summary |
| **C6** | GM Expansion | Complete. 9 functional agents activated with verification |
| **C7** | Sibling Integration | Complete. Event envelope, schema registry, boundary enforcement |
| **C8** | Production Pack | Partial. Gate infrastructure complete; 9 gates need external evidence |

### 3.3 Six Deterministic Engines (C4)

| Engine | Capability | Owning Role | Lines | Adapter |
|--------|-----------|-------------|-------|---------|
| **WFM** | Workforce forecasting, Erlang C | ops_gm | 2,068 | `engines/wfm/adapter.py` |
| **RTA** | Real-time adherence, scheduling | ops_gm | 828 | `engines/rta/adapter.py` |
| **CX** | Churn risk scoring | ops_gm | 1,887 | `engines/cx/adapter.py` |
| **B2B** | B2B onboarding, SOP generation | sales_gm | 1,222 | `engines/b2b/adapter.py` |
| **Personnel** | Hiring pipeline, talent acquisition | hr_personnel_gm | 2,130 | `engines/personnel/adapter.py` |
| **CRM** | Sales pipeline, customer support | sales_gm | 1,166 | `engines/crm/adapter.py` |

### 3.4 Nine Functional Agents (from `organization/role-catalog.yaml`)

SAMI, SUBY, PHILI, WILI, ANDY, NONO, MAYA, LIZA, TOMY

### 3.5 Integration Seam Pattern

`helix_codex_app/integration/` is the **only** package allowed to import parent internals:

| Bridge | Purpose |
|--------|---------|
| `cockpit_bridge.py` | Calls pack `compute_*` functions, no Streamlit import |
| `engine_bridge.py` | App's one door into governed core, authorize-first |
| `memory_bridge.py` | Per-account + per-tenant governed memory stores |
| `metacognition_bridge.py` | Per-store metacognition engines |
| `packs.py` | Capability pack discovery via manifests |
| `policy_bridge.py` | Maps app account to core policy identity |
| `sse_bridge.py` | Wraps parent `server.sse.EventBus` |
| `telemetry.py` | App-to-core telemetry seam |

---

## 4. Package Documentation

### 4.1 `server/` — FastAPI Backend Spine

**Purpose:** The canonical deployable artifact (`helix-api`). All HTTP routes are behind `current_identity` authentication except `/healthz`. The app factory `create_app()` builds: correlation middleware, typed error handlers, kill-switch awareness, and per-request metrics.

**Key Files:**

| File | Lines | Purpose |
|------|-------|---------|
| `__init__.py` | 1 | Module docstring |
| `app.py` | 175 | Application factory — builds all routers, mounts static, error handlers |
| `auth.py` | 132 | Bearer-token auth — HMAC-compares token, assigns tenant/client scope, catalog-driven universal approvers |
| `cli.py` | 30 | Canonical entry point — runs uvicorn on `server.app:create_app` |
| `config.py` | 98 | Pydantic-settings: all env vars prefixed `HELIX_`, profile selection, `require_headless_safe()` |
| `deps.py` | 105 | EngineProvider lifecycle, node_store context manager |
| `errors.py` | 91 | Typed errors: AppError → status code, KillSwitchEngaged → 503 |
| `scope.py` | 118 | Tenant/client scope enforcement, global access audit logging |
| `sse.py` | 94 | EventBus: subscribe/unsubscribe/publish — the only async module |
| `models/node.py` | 164 | Node, NodeEnvelope, Provenance, ChatMessage dataclasses |
| `models/store.py` | 195 | NodeStore: SQLite CRUD with tenant isolation |

**Feature Routers:** health (liveness+readiness), halt (kill switch), chat (SSE streaming), stream (workflow SSE), console (HTMX), docs, tasks, workflows, approvals, metrics.

**Templates:** index.html + partials for chat, docs, tasks, workflows, approvals.

### 4.2 `control_plane/` — Governance Control Plane

**Purpose:** Local-first workflow runtime with SQLite store, governance state machine, kill switch, and organization catalog authority. The Engine is the single orchestrator that enforces all governance controls.

| File | Lines | Purpose |
|------|-------|---------|
| `__init__.py` | 29 | Exports: Workflow, Store, Engine, Handler, ORGANIZATION_CATALOG, etc. |
| `engine.py` | 1,325 | Engine: submit/approve/execute/cancel/rollback — fail-closed on all governance checks |
| `governance.py` | 1,636 | RoleSpec (12 fields), ORGANIZATION_CATALOG (9 seats), evaluate_gate, detect_catalog_drift |
| `store.py` | 667 | Durable SQLite store: atomic append, idempotent creation, WAL mode |
| `workflow.py` | 348 | Workflow state machine: 10 states, valid transitions |
| `events.py` | 154 | Event envelope with hash chain, correlation IDs |
| `kill_switch.py` | 287 | KillSwitch: engage/release/is_engaged — persisted in halt_state table |
| `control_seam.py` | 627 | C5 contact-centre: 9-step pipeline |
| `vertical_slice/__init__.py` | 1,242 | C5 full chain orchestration |
| `schemas/__init__.py` | 129 | Sibling event envelope, dispatch, v1 payloads |
| `schemas/boundary.py` | 201 | Separation boundary: scans imports, fails closed on violations |
| `schemas/envelope.py` | 221 | Event envelope with content digest (SHA-256) |
| `schemas/registry.py` | 336 | JSON schema generation from dataclasses |
| `schemas/v1.py` | 475 | v1 payloads: AssessmentCompleted, CompetencyGapDetected, etc. |

### 4.3 `contracts/` — Typed Agent Contracts

**Purpose:** Shared typed contracts for agent communication, the single SOD implementation, data-mode/classification vocabularies, and generated capability mirrors.

| File | Lines | Purpose |
|------|-------|---------|
| `__init__.py` | 29 | Exports: CorrelationContext, TaskRequest, TaskResult, Recommendation, Action, Approval |
| `task.py` | 988 | Core contracts: CorrelationContext, TaskRequest/Result, Recommendation, Action, Approval, EvidenceRef, AgentError. SCHEMA_VERSION="1.0" |
| `adapter.py` | 209 | C1→C2 seam: parse_legacy_calls, to_task_request, validate_request_against_catalog |
| `segregation_of_duties.py` | 191 | **Single** SOD implementation: self_approval, same_role, unauthorized_reviewer, unauthorized_peer |
| `vocabulary.py` | 348 | Data-mode vocabularies (9 distinct strings), ALL_CLASSIFICATIONS (8), mapping helpers |
| `toolcall.py` | 179 | ToolCall, SideEffect enum, ToolCallResult, ToolDefinition |
| `capabilities.yaml` | 37 | Generated mirror of engine capabilities (canonical: organization/capability-registry.yaml) |

### 4.4 `security/` — Security Module

**Purpose:** Local-first, fail-closed security: tamper-evident audit trail, data classification, identity, authorization policy, injection detection, secrets scanning/redaction.

| File | Lines | Purpose |
|------|-------|---------|
| `__init__.py` | 28 | Exports: DataClassification, Identity, authorize, AuditTrail, verify_chain, etc. |
| `audit.py` | 468 | AuditTrail: append-only, SHA-256 hash chain, verify_chain() |
| `classification.py` | 165 | 6 classification labels: PUBLIC through REGULATED_HIGH_RISK |
| `identity.py` | 79 | Identity dataclass: actor, actor_type, tenant_id, client_id, role_id |
| `policy.py` | 187 | AuthorizationPolicy: authorize() — tenant isolation, role ownership, SOD, deny-by-default |
| `secrets.py` | 174 | Redaction patterns, get_secret(), validate_no_secrets(), redact_dict() |
| `injection.py` | 81 | 8 INJECTION_PATTERNS regexes, is_suspicious_prompt() fail-closed |
| `audit.db` | binary | SQLite audit trail (16,545 records, gitignored) |

### 4.5 `organization/` — Organization/Roles Catalog

**Purpose:** Role catalog loader, capability registry, GM activation. The YAML files are the canonical source of truth; Python modules load them at import.

| File | Lines | Purpose |
|------|-------|---------|
| `__init__.py` | 4 | Exports: load_role_catalog, validate_role_catalog, get_role |
| `role_catalog.py` | 393 | Loads role-catalog.yaml, validates RoleSpec fields, get_role/validate_role_catalog |
| `capability_registry.py` | 376 | CapabilityRegistry: deterministic lookup, loads canonical YAML directly |
| `gm_activation.py` | 365 | activate_gm(): binds validation properties to runtime RoleSpec, refuses unverified GMs |
| `role-catalog.yaml` | 596 | 9 functional agents with full RoleSpec (financial limits, engines, classifications, KPIs, SOD) |
| `capability-registry.yaml` | 52 | 22 capabilities → 5 engines (WFM/RTA/CX/B2B/Personnel/CRM) |

### 4.6 `engines/` — Six Deterministic Engines

Each engine follows identical C4 adapter structure: `ENGINE_ID`, `DISPLAY_NAME`, `CAPABILITY_IDS`, `OWNING_ROLE`, `DATA_CLASSIFICATION`, `_audit()`, `adapt()`.

#### `engines/contracts.py` (523 lines)
Engine adapter contract: EngineResult, ComputationEvidence, FrozenMapping, EngineInvocation dataclasses. DATA_MODE_LIVE/SAMPLE, ENGINE_BASELINE_PAYLOADS.

#### `engines/registry.py` (336 lines)
Engine registry: register_all() wires 6 adapters via _make_handler().

#### `engines/wfm/` (2,068 lines) — Workforce Management
`adapter.py` (493): ENGINE_ID=wfm, CAPABILITY_IDS=wfm_forecast/erlang_c/staffing, OWNING_ROLE=ops_gm
`src/erlang_c.py` (326): Erlang C formula, log-space stable
`src/data_pipeline.py` (472): Extraction, cleaning, validation
`src/app_wfm.py` (598): CLI + UI
`src/variance_engine.py` (671): Statistical variance, anomaly detection

#### `engines/rta/` (828 lines) — Real-Time Adherence
`adapter.py` (452): ENGINE_ID=rta, CAPABILITY_IDS=rta_adherence/schedule, OWNING_ROLE=ops_gm
`src/calculations.py` (629): RTACalculator — adherence math, schedule optimization
`src/app.py` (264): Flask dashboard
`src/visualizations.py` (328): Plotly rendering

#### `engines/cx/` (1,887 lines) — Customer Experience Churn Sentinel
`adapter.py` (456): ENGINE_ID=cx, CAPABILITY_IDS=churn_risk/risk_scoring/cx_monitoring, OWNING_ROLE=ops_gm
`src/risk_scorer.py` (561): 4-KPI churn scoring (CSAT, SLA, FCR, AHT)
`src/kpi_aggregator.py` (359): Normalization, decay, anomaly detection
`src/alert_dispatcher.py` (291): Severity-based routing
`src/dashboard_feed.py` (201): Dashboard payload shaping
`config/risk_thresholds.yaml` (35): Thresholds by severity

#### `engines/personnel/` (2,130 lines) — Personnel
`adapter.py` (412): ENGINE_ID=personnel, CAPABILITY_IDS=talent_acquisition/workforce/hiring, OWNING_ROLE=hr_personnel_gm
`src/pipeline_manager.py` (653): Hiring pipeline stages
`src/talent_acquisition.py` (516): Candidate sourcing, recruitment workflow
`src/workforce_planning.py` (572): Staffing forecasts, skills gap analysis
`src/main.py` (495): Personnel CLI

#### `engines/b2b/` (1,222 lines) — B2B Onboarding
`adapter.py` (423): ENGINE_ID=b2b, CAPABILITY_IDS=b2b_onboarding/sop_generation, OWNING_ROLE=sales_gm
`src/automator.py` (542): Onboarding automator, 5 stages
`src/main.py` (324): B2B CLI
`notion_adapter/notion_adapter.py` (528): Notion REST integration

#### `engines/crm/` (1,166 lines) — CRM
`adapter.py` (426): ENGINE_ID=crm, CAPABILITY_IDS=sales_pipeline/customer_support, OWNING_ROLE=sales_gm
`src/sales_pipeline.py` (605): Lead/Deal/SalesPipeline
`src/customer_support.py` (431): Ticket/SupportSystem

### 4.7 `connectors/` — Provider-Neutral Connectors

**Purpose:** Read-first connectors with governance. All writes go through ConnectorGateway and are AWAITING_APPROVAL by default.

| File | Lines | Purpose |
|------|-------|---------|
| `__init__.py` | 37 | Exports 16 types: Account, ConnectorCapability, SourceRef, etc. |
| `base.py` | 278 | BaseConnector: tenant scope, deterministic rate-limit/retry, write gating |
| `contracts.py` | 236 | ConnectorStatus (7 states), RateLimitPolicy, RetryPolicy, SourceRef, SCHEMA_VERSION="1.0" |
| `policy.py` | 89 | RISK_TIERS (read=1 to write_financial=5), evaluate_write_gate() |
| `ports.py` | 89 | WritePlan, WriteReceipt, ConnectorPort protocol |
| `registry.py` | 49 | ConnectorRegistry: salesforce, zendesk, clay (fake mode only) |
| `fakes.py` | 137 | FakeConnector: deterministic Salesforce/Zendesk/Clay fakes |
| `gateway.py` | 197 | ConnectorGateway: tenant scope, data mode, idempotency, dry-run |
| `LIVE_ADAPTER_CONTRACT.md` | 93 | Live adapter contract documentation |

### 4.8 `helix_codex_app/` — Main App Layer

**Purpose:** The daily-use product layer on top of the governed core. An all-in-one collaboration platform with chat, documents, tasks, calendar, attendance, notifications, and manager-only cockpit. Imports parent core ONLY through `integration/` seam.

**Top-level files:**

| File | Lines | Purpose |
|------|-------|---------|
| `__init__.py` | 6 | Package marker |
| `app.py` | 213 | FastAPI factory: mounts shell/static/routers, account guard + CSRF |
| `cli.py` | 26 | Console entry point: uvicorn on create_app |
| `config.py` | 69 | AppSettings: HELIX_APP_ prefix, loopback-only + insecure-cookie gate |
| `db.py` | 658 | App SQLite: record_node() is the **single writer** for governed nodes |
| `deps.py` | 26 | memory_store_for() provider |
| `errors.py` | 71 | AppError subclasses: AuthError, PermissionDenied, LimitExceeded, etc. |
| `templating.py` | 38 | Single render() function: CSRF token + settings injection |
| `alembic.ini` | 62 | App-local alembic config |
| `governance.md` | 111 | App operating rules + decision log |
| `repomap.md` | 389 | Repo map: folders, routes, tables |
| `agents.md` | 1,449 | Build ledger for app (P0-P7.5) |

**Integration seam** (8 modules — only package allowed to import parent internals):

| Module | Lines | Purpose |
|--------|-------|---------|
| `__init__.py` | 6 | Seam package marker |
| `cockpit_bridge.py` | 168 | Calls pack compute_* functions, no Streamlit |
| `engine_bridge.py` | 343 | App's door into governed core, authorize-first, fail-closed |
| `memory_bridge.py` | 298 | Account + org governed memory stores |
| `metacognition_bridge.py` | 173 | Per-store metacognition engines |
| `packs.py` | 151 | Capability pack discovery via manifests |
| `policy_bridge.py` | 154 | Maps app account to core policy identity |
| `sse_bridge.py` | 57 | Wraps parent EventBus |
| `telemetry.py` | 28 | App-to-core telemetry |

**App security** (7 modules):

| Module | Purpose |
|--------|---------|
| `security/accounts.py` | Domain, OrgUnit, Account + AccountRepository |
| `security/guard.py` | current_account, require_csrf, require_permission |
| `security/limits.py` | Role-based defaults + quota consumption |
| `security/passwords.py` | Hash + verify via stdlib scrypt |
| `security/permissions.py` | Permission matrix across 5 app roles |
| `security/sessions.py` | Opaque session tokens, CSRF double-submit, revocation |
| `security/throttle.py` | SQLite-backed login throttle (added 2026-09-18) |

**App modules** (14 feature modules, each with repository/service/router):

| Module | Purpose |
|--------|---------|
| `admin/` | User/domain/org unit management (owner-only) |
| `attendance/` | Punch in/out, records, summary |
| `calendar/` | Events, RSVPs, on-call coverage |
| `cockpit/` | Owner/coach/parent dashboards |
| `docs/` | Documents, editor, KB, versions |
| `identity/` | Login, logout, password change |
| `lowcode/` | Pack loader, section registry |
| `memory/` | Proposals, reviews, promotion |
| `messaging/` | Chat: conversations, messages, SSE stream, cursor paging |
| `notifications/` | Notifications, badge, SSE stream |
| `ops/` | Engine overview, workflow governance |
| `tasks/` | Task board, lifecycle, steward gate |
| `evidence.py` | Evidence zip builder for tenant dossier |

**Templates:** 30+ Jinja2 files including base.html, shell/home.html, auth/*, admin/*, and per-feature screens.

**Static assets:** CSS (tokens, app, fonts), JS (shell, sse, docs, notifications, pwa, tasks), SVG icons, PWA icons (192/512/maskable), manifest.webmanifest, sw.js, offline.html, vendored Alpine.js + HTMX, self-hosted woff2 fonts (Instrument Sans/Serif, JetBrains Mono).

### 4.9 `cockpit/` — Streamlit Dashboard (Secondary)

| File | Lines | Purpose |
|------|-------|---------|
| `__init__.py` | 0 | Package marker |
| `cli.py` | 32 | Console entry: streamlit run cockpit/cockpit.py |
| `cockpit.py` | 1,029 | Legacy operations control room: 9 agents, 6 engines, dashboard, control plane, Codex, agents, engines, memory, system status, client simulation |
| `codex_command_center.py` | 248 | Codex Command Center shell |
| `command_center_integration.py` | 385 | Pure assembly: evaluate_approval, assemble_command_center, NO Streamlit import |
| `RELEASE_README.md` | 35 | Release notes for v0.1.0 |

### 4.10 `memory/` — Governed Memory

| File | Lines | Purpose |
|------|-------|---------|
| `__init__.py` | 0 | Package marker |
| `governed_memory.py` | 567 | GovernedMemory: append-only, hash-chained, tenant-isolated, classification-aware, retention as soft tombstones |

Key methods: add(), retrieve(), correct(), supersede(), delete(), clear_for_demo(), verify_chain(), audit_status(), list_records(), apply_retention(). Constants: CLASSIFICATION_LEVELS (6), NATURES (6: verified_fact, user_claim, model_inference, simulated_event, historical_event, verified_outcome), KINDS (9).

### 4.11 `metacognition/` — Improvement Proposals

| File | Lines | Purpose |
|------|-------|---------|
| `__init__.py` | 0 | Package marker |
| `improvement.py` | 494 | MetacognitionEngine: detect failures → propose improvements → evaluate vs baselines → approve/reject/rollback. NEVER modifies production behavior. Proposal states: DRAFT/EVALUATING/EVALUATED/EVALUATED_FAILED/REJECTED/APPROVED/ROLLED_BACK. |

### 4.12 `observability/` — Observability

| File | Lines | Purpose |
|------|-------|---------|
| `__init__.py` | 5 | Exports: log_structured, get_logger, check_health, HealthStatus |
| `health.py` | 169 | 6-component health checks: control_plane_store, event_replay, capability_registry, role_catalog, ollama, filesystem |
| `logging.py` | 110 | Structured JSON logging → observability/logs.jsonl (26 optional fields) |
| `metrics.py` | 385 | Stdlib-only Prometheus registry: helix_http_requests_total, helix_http_request_duration_seconds, helix_governance_decisions_total, helix_audit_chain_verifications_total, helix_audit_chain_verification_failures, helix_approval_queue_depth, helix_readiness_check_failures_total, helix_auth_events_total, helix_kill_switch_events_total, helix_data_disk_free_bytes |

### 4.13 `pilot/` — Controlled Pilot Engine

| File | Lines | Purpose |
|------|-------|---------|
| `__init__.py` | 41 | Exports: PilotConfig, ConsentRecord, PilotRuntime, PilotScope, etc. |
| `run.py` | 526 | PilotRuntime: diagnose/submit/approve/execute/generate_metacognitive_proposal/final_status |
| `approval.py` | 147 | Recommendation → approval draft → transition via evaluate_approval_decision |
| `config.py` | 45 | PilotConfig: read-only-first, minimum-data, tenant isolation |
| `consent.py` | 38 | ConsentRecord + validate_consent() |
| `evidence_pack.py` | 90 | build_evidence_pack() |
| `exceptions.py` | 6 | PilotError |
| `metrics.py` | 73 | 8 pilot success metrics |
| `phases.py` | 49 | ReadOnlyPeriod, ConnectorPermissions: READ_ONLY/SUPERVISED/CLOSED |
| `scope.py` | 146 | PilotScope, DataClassificationPolicy, MinimumDataPolicy, TenantIsolationConfig |

### 4.14 `customer_success/` — Account Health Wedge

| File | Lines | Purpose |
|------|-------|---------|
| `__init__.py` | 36 | Exports: AccountHealthAssessment, assess_account_health, build_approval_preview, diagnose, run_wedge, etc. |
| `wedge.py` | 540 | Main wedge: account context → diagnosis → recommendation → approval preview → outcome in memory |
| `health.py` | 104 | Deterministic scoring: SLA breach −25, high-priority open −10, score 0-100 |
| `fixtures.py` | 197 | Deterministic fixture builders |

### 4.15 `capabilities/` — Capability Packs

#### `capabilities/restaurant/` (Reference pack — pattern to copy from)
8 files: __init__, classifications, contracts, fixtures, metrics, ontology, policies, register, roles, runtime, workflows.

#### `capabilities/sports_academy/` (Scoach Academy Hub pack)
19 files across 5 subdirectories:
- Root: __init__ (116), capability.yaml (20), classifications (11), contracts (95), fixtures (270), kpis (171), ontology (102), register (96), roles (41), runtime (620), workflows (177)
- adapters/: __init__ (28), attendance_adapter (237), athlete_profile_adapter (229), facility_adapter (73), payment_adapter (112)
- cockpit_views/: __init__ (7), owner_dashboard (102), coach_dashboard (103), parent_portal (112)
- declarations/: academy_kpis.yaml (42), coach_kpis.yaml (37), academy_roles.yaml (43), enrollment_flow.yaml (30), attendance_flow.yaml (23), renewal_flow.yaml (29)

### 4.16 `release/` — Release/Gating System

| File | Lines | Purpose |
|------|-------|---------|
| `__init__.py` | 10 | Release package init |
| `gate.py` | 704 | Core release gate: 23 gates (14 C8 + app + 9 production-only), profiles, classification, exit codes |
| `harness.py` | 430 | Gate harness: evidence writing, probes, disposables |
| `profiles.py` | 202 | Gate profiles — DERIVED from release-profiles.yaml (14 gates × 4 profiles) |
| `production_evidence.py` | 293 | Evidence verifier: RSA-PKCS#1 v1.5 signature check over external artifacts |
| `signoff.py` | 202 | Sign-off serialization + validation: validate_signoff, import_go_no_go |
| `backup.py` | 220 | Backup logic |
| `observability.py` | 132 | Observability gate + report |
| `security_gate.py` | 260 | Security gate evaluation |
| `manifest.py` | 156 | Manifest generation; version single-sourced from pyproject.toml via tomllib |
| `pilot_metrics.py` | 128 | Pilot metrics |
| `release-profiles.yaml` | 146 | **Source of truth** for gate profiles + allowed_final (includes PRODUCTION) |
| `release-manifest.json` | 50 | Last manifest (pins b6b954e; release_approved: false — deliberately stale) |
| `go-no-go.json` | 15 | Pilot consent flag (approved: true; NOT a human production approval) |
| `manifest.schema.json` | 69 | Schema: profiles + classifications enums |
| `requirements.lock.txt` | 339 | Locked dependencies (120 real pins + comments) |

### 4.17 `scripts/` — Operational Scripts

| File | Lines | Purpose |
|------|-------|---------|
| `check_dependencies.py` | 232 | Enforces: nothing declares deps outside requirements.txt + requirements-dev.txt |
| `check_governance_drift.py` | 144 | Governance drift checker: --json, fail-closed, CI-wired |
| `check_migration_drift.py` | 159 | Alembic drift: Store DB vs alembic DB, compares sqlite_master |
| `sync_capability_mirrors.py` | 234 | Mirror sync: only writer, --check in CI |
| `export_evidence_pack.py` | 196 | Evidence pack exporter (read-only) |
| `produce_production_evidence.py` | 355 | Evidence producer: gates, init-key, template, check, sign, status |
| `record_production_signoff.py` | 188 | Sign-off recorder: states, template, check |
| `kill_switch.py` | 65 | Kill switch CLI: engage/release/status |
| `smoke.py` | 138 | Smoke test runner |
| `pilot_dry_run.py` | 343 | Pilot dry run |
| `release_gate.py` | 28 | Release gate runner (warns NOT read-only) |
| `health_check.py` | 24 | Health check script |
| `sync_role_metadata.py` | 146 | Role metadata sync |

### 4.18 `tests/` — Test Directory (~62 root files, ~42K lines)

| File | Lines | Purpose |
|------|-------|---------|
| `conftest.py` | 104 | Shared fixtures and configuration |
| `test_c1_contracts.py` | 1,278 | C1 contract compliance, catalog drift, SOD governance |
| `test_c2_control_plane.py` | 911 | Control plane behavior |
| `test_c2_preflight_regression.py` | 262 | Preflight regression |
| `test_c3_c2_integration_preflight.py` | 289 | C3↔C2 integration preflight |
| `test_c3_security.py` | 712 | Security tests |
| `test_c4_engines.py` | 943 | Engine productization |
| `test_c5_vertical_slice.py` | 645 | Vertical slice regression |
| `test_c6_gm_expansion.py` | 558 | GM expansion |
| `test_c7_sibling_integration.py` | 556 | Sibling integration |
| `test_c8_gate_falsifiability.py` | 393 | Falsifiability proofs: 35 tests × 7 gates |
| `test_c8_release_gate.py` | 575 | Release gate tests: 28 tests incl. schema validation |
| `test_call_centre_proving_workflow.py` | 365 | Call-centre proving workflow |
| `test_capabilities_restaurant.py` | 261 | Restaurant pack |
| `test_capabilities_sports_academy.py` | 713 | Sports academy pack: 44 tests |
| `test_capability_registry_drift.py` | 51 | Capability registry mirror drift |
| `test_chat_stream.py` | 217 | Chat SSE streaming: 9 tests |
| `test_cloud_readiness.py` | 141 | Cloud deployment readiness |
| `test_cockpit_client_profiles.py` | 69 | Cockpit client profiles |
| `test_command_center_integration.py` | 250 | Command center (write_evidence=False) |
| `test_connectors.py` | 31 | Connector tests |
| `test_connectors_layer.py` | 238 | Connector layer |
| `test_connectors_write_path.py` | 167 | Connector write path |
| `test_control_seam.py` | 192 | Control seam |
| `test_customer_success.py` | 22 | Customer success |
| `test_customer_success_wedge.py` | 174 | Customer success wedge |
| `test_engine_audit_perf.py` | 113 | Engine audit performance |
| `test_governance_catalog_source.py` | 285 | Governance catalog = YAML source proofs: 28 tests |
| `test_governance_fail_closed.py` | 24 | Governance fail-closed |
| `test_governance.py` | 16 | Governance |
| `test_governed_memory.py` | 478 | Governed memory behavior |
| `test_helix_codex_app_db.py` | 240 | App DB envelope: 16 tests |
| `test_kill_switch.py` | 258 | Kill switch: 12 tests |
| `test_metacognition.py` | 240 | Metacognition engine |
| `test_metrics.py` | 258 | Metrics + alert drift: 13 tests |
| `test_migration_drift.py` | 113 | Alembic migration drift: 7 tests |
| `test_pack_readiness_contract.py` | 67 | Pack readiness contract |
| `test_pilot.py` | 320 | Pilot tests |
| `test_pilot_readiness.py` | 243 | Pilot readiness: 27 tests |
| `test_produce_production_evidence.py` | 172 | Evidence producer tests |
| `test_production_data_boundary.py` | 176 | Production data boundary: 12 tests |
| `test_production_evidence.py` | 279 | Production evidence verification: 27 tests |
| `test_record_production_signoff.py` | 124 | Sign-off recorder tests |
| `test_segregation_of_duties.py` | 776 | SOD delegation proofs: 70 tests |
| `test_server_auth.py` | 62 | Server auth |
| `test_server_spine.py` | 202 | FastAPI spine: 12 tests |
| `test_service_readiness.py` | 110 | /readyz fail-closed: 7 tests |
| `test_sod_integrity.py` | 210 | SOD integrity |
| `test_vocabulary.py` | 271 | Vocabulary single-sourcing: 45 tests |
| `tests/fixtures/` | — | C5 fixtures + production evidence (18 files) |
| `tests/support/sqlite_harness.py` | 195 | SQLite store fixture |

### 4.19 `tests/helix_codex_app/` — App-Specific Tests (52 files, ~13K lines)

Key test files: test_auth_hardening (227), test_integration_seam (70), test_messaging (403), test_messaging_routes (365), test_app_packaging (184), test_app_release_gates (124), test_backup_procedure (252), test_admin (414), test_attendance (401), test_calendar (396), test_docs (324), test_login_and_auth (287), test_ledger_verify (99), test_evidence_backup_restore (293), test_oncall (462), test_tasks (265), test_permissions_and_policy_bridge (125), test_proposal_lifecycle (96), test_sessions_and_guard (231), test_memory_* (3 files), test_notifications_* (3 files), test_ops_* (2 files), test_pwa_assets (38), test_engine_bridge_* (2 files), test_sse_isolation (171), test_tenant_isolation (163), plus more.

---

## 5. Key Files Reference

### 5.1 Configuration Files

| File | Purpose | Key Content |
|------|---------|-------------|
| `pyproject.toml` | Single source of truth | Build (hatchling), deps (14 runtime, hard upper bounds), entry points (helix-api canonical), ruff (E4/E7/E9/F/I/B/S, line 100), mypy (13 disabled), bandit (skip B113/B310/B608), pytest (-m "not smoke", pythonpath) |
| `requirements.txt` | Runtime deps | pydantic, PyYAML, alembic, pandas/numpy/scipy/scikit-learn, streamlit, Flask/CORS, ollama, python-multipart |
| `requirements-dev.txt` | Dev tooling | pytest 7.4-10, ruff 0.1.15, mypy 1.8, bandit 1.7, pip-audit 2.6, flake8, pre-commit |
| `release/requirements.lock.txt` | Locked deps | 120 real pins + 219 comment lines |
| `alembic.ini` | Alembic config | No URL stored; DB path via -x db= override |
| `bandit.yaml` | Bandit config | Skips B113, B310, B608 |
| `.pre-commit-config.yaml` | Pre-commit hooks | Ruff (lint+format), trailing-whitespace, eof-fixer, check-yaml, large-files, merge-conflict, private-key |
| `.gitattributes` | Git LFS | marketing/assets/fonts/*.ttf filter=lfs |
| `.gitignore` | Git ignore | Excludes __pycache__, .db, .venv*, .pytest, coverage, etc. |
| `.flake8` | Flake8 config | max-line-length=100, superseded by ruff |

### 5.2 CI/CD

`.github/workflows/ci.yml` (88 lines): push/PR to main, ubuntu-latest, Python 3.12, steps:
1. Checkout (with LFS)
2. Install from `release/requirements.lock.txt` + `requirements-dev.txt`
3. Ruff lint (17 shipped dirs) → `ruff check .`
4. Ruff format check → `ruff format --check .`
5. Mypy: `server/ connectors/ control_plane/ contracts/ security/` (72 files)
6. Test suite: `pytest tests/ -q -m "not smoke" --cov=server --cov=connectors --cov-fail-under=80`
7. Bandit (-ll) + pip-audit on lock
8. `scripts/check_dependencies.py`
9. `scripts/check_migration_drift.py`
10. `scripts/check_governance_drift.py`
11. `scripts/sync_capability_mirrors.py --check`
12. `python GOVERNANCE/governance_check.py check`
13. `python -m build`

`.github/workflows/python-publish.yml` (24 lines): on release:published → build sdist+wheel → GitHub artifact.

### 5.3 Docker Configuration

| File | Lines | Purpose |
|------|-------|---------|
| `infra/docker/Dockerfile` | 55 | Base image |
| `infra/docker/Dockerfile.app` | 57 | App image: pinned lock, strict non-root (no root/0 USER) |
| `infra/docker/docker-compose.yml` | 78 | App + DB, stop_grace_period: 30s, liveness-only healthcheck |
| `infra/docker/docker-compose.app.yml` | 45 | App-only compose |
| `infra/docker/entrypoint.sh` | 16 | Entrypoint script |

### 5.4 Monitoring Configuration

| File | Lines | Purpose |
|------|-------|---------|
| `infra/monitoring/README.md` | 78 | Full metric table + alert catalog |
| `infra/monitoring/alerts.yml` | 165 | Prometheus rules: scrape-down, 5xx ratio, p95 latency, governance denial, audit-chain failure, queue backlog |

---

## 6. Production Readiness

### 6.1 Current Status

| Label | Achieved | Gate Result |
|-------|----------|-------------|
| **app_pilot** | ✅ | CONTROLLED_PILOT_READY |
| **controlled_pilot** | ✅ | CONTROLLED_PILOT_READY |
| **production_candidate** | ✅ | PRODUCTION_CANDIDATE |
| **production** | ❌ | NOT_READY (9 gates need external evidence) |

### 6.2 The 23 Gates (in release/gate.py)

**14 C8 Gates:** configuration_validation, startup_readiness, backup_restore, rollback, data_isolation, operator_readiness, audit_integrity, security_checks, failure_recovery, performance_limits, repository_state, dependency_locking, reproducible_install, app_session_fail_closed

**App Gates:** app_pilot (and related app-specific gates)

**9 Production-Only Gates (B1):** signed_production_evidence, certified_data_isolation, external_observer_audit, production_deployment_architecture, disaster_recovery_evidence, operational_ownership, incident_oncall_ownership, security_review, legal_privacy_review

### 6.3 What's Blocking Production

The 9 production-only gates are **not** code-blocked — they are **evidence-blocked**. Each requires a detached RSA-signed artifact from outside the repository. B1 built both the consumer (`release/production_evidence.py`) and the producer (`scripts/produce_production_evidence.py`). B2 also built the sign-off recorder (`scripts/record_production_signoff.py`).

With nine signed evidence fixtures in place, `run_gate(profile="production")` achieves **23/23 gates green**, classification **PRODUCTION**, terminal record **valid** — but the label still requires a real human `production_approved` record signed by named external parties.

### 6.4 What Changed in GOV-1 (2026-09-19/20)

| Phase | What | Status |
|-------|------|--------|
| **A0** | Correctness fixes: dead universal_approvers, duplicate validation, hardcoded literals, drift set pinned (test pins exact field/role/count set), both governance checks wired into CI (new script + CI steps) | COMPLETE |
| **A1** | Vocabulary single-sourcing: new contracts/vocabulary.py (9 data modes, 8 classifications), migrated 15 module-level copies, frozen files pinned by test | COMPLETE |
| **A2** | Structural mirror removal: governance.py sources 4 structural fields from YAML, FINANCIAL_LIMIT_OVERRIDES declares 8 stricter ceilings, mirrors become build artifacts via scripts/sync_capability_mirrors.py | COMPLETE |
| **A3+A4** | SOD unified to one implementation (contracts/segregation_of_duties.py, 70 delegation-proof tests), dead code cleaned (unreachable branch deleted, duplicate if removed, RoleSpec.to_dict() projects all 12 fields, app node envelope validates vocabularies) | COMPLETE |
| **B1** | Production evidence loader: release/production_evidence.py (verifier), producer scripts, server/gate agree by construction, sign-off test became red/green pair | COMPLETE |
| **B2-B4** | Infrastructure spend, paid external parties, legal/human authority | **NOT STARTED** (owner-driven) |

### 6.5 Honest Assessment

| Dimension | Status | Notes |
|-----------|--------|-------|
| Code quality | ✅ Strong | 1,758 tests passing, ruff clean, mypy clean, bandit clean |
| Architecture | ✅ Sound | Layered, seam-governed, no circular imports in core |
| Governance | ✅ Implemented | 23 gates, 9 production-only, fail-closed everywhere |
| Testing | ✅ Comprehensive | 1,758 tests, 0 failing, 0 skipped |
| Security posture | ✅ Good | Audit trail, classification, injection detection, secrets scanning, auth hardening |
| Documentation | ✅ Extensive | ~60K lines across docs/ + governance docs |
| **Production readiness** | **NOT ESTABLISHED** | Needs 9 external signatures + human sign-off |
| **Commercial status** | **Controlled pilot** | Single client (Scoach Academy Hub), synthetic data |

---

## 7. Security and Hygiene

### 7.1 Security Architecture

| Layer | Mechanism | File |
|-------|-----------|------|
| Authentication | Bearer tokens (HMAC), tenant/client scope | server/auth.py |
| Authorization | Deny-by-default policy, RBAC, SOD | security/policy.py, contracts/segregation_of_duties.py |
| Audit | Append-only SHA-256 hash chain | security/audit.py |
| Classification | 6 labels, validated at every boundary | security/classification.py |
| Injection | 8 pattern detectors, fail-closed | security/injection.py |
| Secrets | Redaction patterns, validation, no-scan | security/secrets.py |
| Rate limiting | SQLite-backed throttle (app) | helix_codex_app/security/throttle.py |
| Session security | Opaque tokens, CSRF double-submit, revocation | helix_codex_app/security/sessions.py |
| Password security | scrypt hashing | helix_codex_app/security/passwords.py |
| Kill switch | Emergency halt, persisted, audit-recorded | control_plane/kill_switch.py |

### 7.2 CI Security Scans

| Tool | Configuration | Result |
|------|--------------|--------|
| Bandit | -ll level, skips B113/B310/B608 (documented) | No issues |
| pip-audit | On lock file | Clean |
| Dependabot | Weekly pip + github-actions | Active |
| Pre-commit | Ruff + standard hooks | Configured (not auto-installed locally) |

### 7.3 Hygiene Notes

- **No secrets committed**: git history scanned, no .env, no cookies, no private keys (one .pem is a public test key)
- **No uncommitted .db files**: both SQLite DBs are gitignored
- **No __pycache__ in git**: gitignored
- **Fonts on Git LFS**: 3 DejaVu TTFs (~1.8MB) via .gitattributes
- **Test hygiene**: tests use write_evidence=False on gate probes to avoid touching tracked manifest
- **Delete guard awareness**: Windows sandbox has cumulative bulk-delete guard (threshold 50 by default); raise CODEBUDDY_SAFE_DELETE_BULK_THRESHOLD for full-suite runs

### 7.4 Known Security Considerations

- `pilot/*` files are on the Do-NOT-touch list (frozen governance)
- `organization/role-catalog.yaml` is canonical source of truth (not editable at runtime)
- Release manifest deliberately left stale (release_approved: false) until real ceremony runs
- Production evidence requires external signatures; no private key in repo

---

## 8. Workflow and CI/CD

### 8.1 Development Workflow

1. **Setup**: `setup.sh` / `setup.bat` → create .venv-py312, install requirements
2. **Code**: Edit files following existing patterns (reference: `capabilities/restaurant/`)
3. **Test**: `CODEBUDDY_SAFE_DELETE_BULK_THRESHOLD=100000 .venv-py312/Scripts/python.exe -m pytest tests/ -q -m "not smoke" --junitxml=E:/hx/full.xml`
4. **Lint**: `ruff check <paths>` → 0 findings; `ruff format --check <paths>` → clean
5. **Typecheck**: `mypy server/ connectors/ control_plane/` → no issues
6. **Commit**: Conventional commits (`feat(academy): ...`, `test(academy): ...`, `docs: ...`)
7. **Push**: Requires owner decision (the repository is private; the push itself is the only remaining owner action)

### 8.2 Release Workflow

1. Produce evidence artifacts: `scripts/produce_production_evidence.py` → gates, init-key, template, check, sign, status
2. Record sign-off: `scripts/record_production_signoff.py` → states, template, check
3. Run gate: `scripts/release_gate.py` (warns: NOT read-only — regenerates manifest)
4. Verify: All 23 gates green on evidence → classification PRODUCTION → exit 0 (with allowed_final including PRODUCTION)
5. Publish: Manual PyPI upload from dist/ artifact

### 8.3 Deployment Options

| Path | Command | Purpose |
|------|---------|---------|
| **Canonical** | `helix-api` | FastAPI spine on 127.0.0.1:8000 (helix-api entry point) |
| Secondary | `helix-cockpit` | Streamlit dashboard on 127.0.0.1:8501 |
| Legacy | `launch.py` | Streamlit operations cockpit with health wait |
| Legacy | `launch.bat` | Windows launcher for cockpit |
| Docker | `docker-compose.app.yml` | App-only container |
| Dev | `python -m uvicorn server.app:create_app` | Direct uvicorn |

---

## 9. Testing

### 9.1 Test Summary

| Metric | Value |
|--------|-------|
| Total collected | 1,743 |
| Passing | 1,743 |
| Failing | 0 |
| Skipped | 0 |
| Test files (root) | ~62 |
| Test files (app) | 52 |
| Full-suite runtime | ~17-40 minutes (varies by sandbox conditions) |

### 9.2 Test Categories

| Category | Files | Count | Purpose |
|----------|-------|-------|---------|
| C0-C8 governance | test_c1_contracts, test_c2_*, test_c3_*, test_c4_engines, test_c5_*, test_c6_*, test_c7_*, test_c8_* | ~5,600 lines | Governance gate verification |
| Falsifiability | test_c8_gate_falsifiability | 35 tests | Prove each gate can fail |
| SOD | test_segregation_of_duties | 70 tests | Delegation proof per site |
| Production | test_production_evidence, test_record_production_signoff, test_production_data_boundary | ~580 lines | Evidence pipeline verification |
| Vocabulary | test_vocabulary | 45 tests | Single-sourcing proof |
| App | tests/helix_codex_app/* | 52 files | App layer behavior |
| Packs | test_capabilities_restaurant, test_capabilities_sports_academy | ~970 lines | Capability pack tests |
| Integration | test_command_center_integration, test_chat_stream, test_connectors_* | Multiple | End-to-end integration |

### 9.3 Ruff Configuration

```
select = E4/E7/E9/F/I/B/S
line-length = 100
extend-immutable-calls = ["fastapi.Depends"]
per-file-ignores: legacy debt and test-idiomatic patterns
```

Result: **0 findings** across all shipped code, `ruff format --check .` clean.

### 9.4 Mypy Configuration

```
[mypy] python_version = 3.12
disable_error_code = 13 codes (var-annotated, call-overload, attr-defined, assignment, arg-type, operator, call-arg, type-var, dict-item, union-attr, truthy-function, index, override)
```

Scope: `server/ connectors/ control_plane/ contracts/ security/` → **no issues in 72 source files**.

---

## 10. Documentation Landscape

### 10.1 Document Categories

| Category | Location | Count | Purpose |
|----------|----------|-------|---------|
| Authority documents | Root + docs/ | 3 | Constitution, blueprint, master story |
| Architecture docs | docs/architecture/, docs/ | ~10 | System architecture, repo graph |
| Operational docs | docs/operations/, docs/release/ | ~25 | Runbooks, data retention, backups, pilot protocol |
| Strategic docs | docs/portfolio/ | 17 | Business case, market research, limitations |
| Governance docs | GOVERNANCE/ | 22 | Implementation matrix, tickets, workspace map |
| Release docs | docs/release/, release/ | ~20 | Signoff, blockers, handoff, production boundary |
| Audit docs | docs/audits/ | 3 | Audit plans, re-evaluations |
| Visual handoff | docs/handoff/ | 30+ | Dashboards, specs, validation reports |
| Build ledger | AGENTS.md | 4,500+ lines | Complete operational handoff |
| Changelog | CHANGELOG.md | 203 lines | Release history |

### 10.2 Living vs. Archived Documents

**Living**: README.md, docs/HELIX_CODED_OS_MASTER_BLUEPRINT.md, docs/scoach_academy_hub_opportunity_report.md, AGENTS.md, CHANGELOG.md, docs/release/*, docs/operations/*

**Archived** (SUPERSEDED banners, in docs/archive/): GAP_ANALYSIS.md, HELIX_CODEX_UPGRADE_PLAN.md, PHASE1_BASELINE.md (now in docs/), docs/portfolio/15_verified_test_results.md

### 10.3 Link Integrity

Link crawler verified: **0 broken relative links** across all tracked .md files.

### 10.4 Stale Fact Corrections (applied)

- Test counts updated: 445 → 620 → 1483 → 1743 → 1,758 (H3.2, GOV-1; 2026-09-20)
- Unpushed-commit delta: 4 → 166 → 19 → 7. The 166 and 19 figures were both measured against a remembered commit hash (`3055bb2`) rather than against `origin/main`; the remote had since advanced to `b9d8fb6`. 7 is the measured value at HEAD against the live remote.
- Agent count: "four" → "nine" (PRODUCT_DEFINITION.md, COMMERCIAL_STORY.md)
- Python baseline: 3.10 → 3.12 (PHASE1_BASELINE.md → SUPERSEDED)
- Release manifest fields: dependency_lock_count 333 → 120 recorded (different metric), git_commit/build_timestamp recorded as historical
- Docs/release/production-blockers.md: "red by construction" → "red absent signed evidence"

---

## 11. Governance

### 11.1 Authority Chain

```
00_CONSTITUTION.md (supreme authority)
  → docs/HELIX_CODED_OS_MASTER_BLUEPRINT.md (architecture + commercial record)
    → implementation (code)
      → docs/*.md, README.md, ROADMAP.md, MASTER_STORY.md (subordinate records)
```

### 11.2 Governance Checks in CI

| Step | Script | Purpose |
|------|--------|---------|
| Governance catalog drift | `scripts/check_governance_drift.py` | Detects structural/role/financial drift |
| Governance authority | `python GOVERNANCE/governance_check.py check` | 3/3 validation |
| Capability mirror sync | `scripts/sync_capability_mirrors.py --check` | 22 engine mappings match canonical |
| Migration drift | `scripts/check_migration_drift.py` | Store vs alembic DDL comparison |
| Dependency check | `scripts/check_dependencies.py` | No undeclared deps |

### 11.3 Key Governance Decisions

| Decision | Rationale |
|----------|-----------|
| Deleted control_plane/tenancy.py (H1.4) | Zero references, zero tests, gate uses security.policy.authorize instead |
| universal_approvers sourced from catalog (A0.1) | Was always [] — control never fired; now validated and propagated |
| SOD unified to contracts/segregation_of_duties.py (A3) | 7 sites, identical reason strings → single implementation with delegation proofs |
| release-profiles.yaml is source of truth (B1) | Module derives from YAML, not vice versa; changing YAML changes behavior |
| allowed_final includes PRODUCTION (owner decision) | Gates still block unevidenced production; only fully-evidenced path exits 0 |
| production evidence lives outside repo | Attested system must not hold attestation key |
| production_approved signoff is human act | No code automation for the terminal human approval |

### 11.4 Frozen Gates (do not modify bodies)

release/gate.py bodies for _gate_audit_integrity, _gate_security_checks, _gate_failure_recovery, _gate_performance_limits are SHA-256 pinned in test_c8_gate_falsifiability.py. Window numbers may drift; bodies are byte-identical between origin/main and HEAD.

---

## 12. Deployment

### 12.1 Quick Start

```bash
# Setup
python -m venv .venv-py312
.venv-py312/Scripts/pip install -r requirements.txt -r requirements-dev.txt

# Run canonical API
helix-api  # or: uvicorn server.app:create_app --host 127.0.0.1 --port 8000

# Run cockpit (secondary)
helix-cockpit  # or: streamlit run cockpit/cockpit.py

# Run tests
.venv-py312/Scripts/python -m pytest tests/ -q -m "not smoke"

# Lint
ruff check .
ruff format --check .
mypy server/ connectors/ control_plane/
```

### 12.2 Docker Deployment

```bash
docker compose -f infra/docker/docker-compose.app.yml up
```

### 12.3 Artifact Building

```bash
python -m build
```

Produces sdist + wheel in dist/. Entry point `helix-api` is canonical.

### 12.4 Repository Access Notice

⚠️ The repository is **private** (GitHub: HatemIsmailShalaby1979/Helix-Prime); the owner changed it from public on 2026-09-21, so access is restricted to authenticated collaborators and everything committed is no longer world-readable. Two caveats carry over from the public period. First, the ~174 commits published while the repository was public are **not** un-published — private hides content from new anonymous readers and does not retract what was already fetched. Second, internal-only material (status documents, client names, commercial figures) therefore still exists in that fetched history. The last public push published docs/handoff/00-project-handover.html, docs/Helix_Codex_System_Analysis_and_Design.pdf, docs/client_one_pager.md, docs/scoach_academy_hub_opportunity_report.md. No secrets were found in the content scan; internal material disclosure remains a governance consideration, now mitigated by restricted access rather than by retraction.

---

## 13. Appendix

### 13.1 Environment Facts

| Item | Value |
|------|-------|
| Working venv | `.venv-py312/Scripts/python.exe` (3.12.10) |
| Ruff version | 0.1.15 |
| Full-suite baseline | 571 tests (S0) → 1,743 (GOV-1) |
| Full-suite runtime | 17-40 minutes (varies by sandbox) |
| Test command | `python -m pytest tests/ -q -m "not smoke"` |
| Windows note | pytest always uses `\\?\` path on Windows; bulk-delete guard threshold 50; raise CODEBUDDY_SAFE_DELETE_BULK_THRESHOLD for full runs |
| Python hash randomization | Deterministic fixtures use random.Random(42), not hash() |
| Font MIME | Python mimetypes has no .woff2 entry; server registers it |

### 13.2 Key Data Points

| Metric | Value |
|--------|-------|
| Sports academy MRR | 7,960 (20 U12×200 + 18 U15×220) |
| Active athletes | 38 (out of 40 total) |
| Attendance rate | 0.812 (216/266 expected slots) |
| At-risk athletes | 7 (attendance < 0.6) |
| Facility utilization | 0.6667 (14 booked/21 total) |
| Pack version | 1.0.0 |
| Core version | 0.9.0 |
| Agents | 9 (SAMI, SUBY, PHILI, WILI, ANDY, NONO, MAYA, LIZA, TOMY) |
| Engines | 6 (WFM, RTA, CX, B2B, Personnel, CRM) |
| Roles (core) | 9 (from role-catalog.yaml) |
| Roles (sports academy) | 5 (academy_owner, head_coach, coach, academy_admin, parent) |
| Data modes | 9 distinct strings |
| Classifications | 8 distinct strings |

### 13.3 Repository Statistics

| Metric | Value |
|--------|-------|
| Estimated total Python lines | ~150,000+ |
| Python files (approx.) | 600+ |
| Documentation lines | ~60,000 |
| Test lines (root + app) | ~55,000 |
| Markdown files | ~200+ |
| JSON/YAML/TOML config files | ~50+ |
| Git commits | 174+ (174 local, all unpublished as of HEAD) |
| Branches | main, h01-rta-hardening, h02-server-bind, worktree-phase2-collaboration |

### 13.4 Decision: Do-NOT-Touch List

The following are protected from code changes by test pinning or explicit decision:

- `organization/role-catalog.yaml` — canonical role source
- `control_plane/governance.py` — governed catalog (frozen gate bodies specifically)
- `organization/capability-registry.yaml` — canonical capability source
- `pilot/*` — frozen pilot governance (verdicts pinned to equality tests)
- `release/requirements.lock.txt` — pinned dependencies
- `00_CONSTITUTION.md` — supreme authority
- `release/release-manifest.json` — deliberately stale until real ceremony
- `release/go-no-go.json` — pilot consent flag (human act to update)

### 13.5 How to Convert This Document to PDF

This document is written in Markdown. To produce a PDF:

1. **Pandoc** (recommended): `pandoc docs/PROJECT_ARCHITECTURE.md -o docs/PROJECT_ARCHITECTURE.pdf --pdf-engine=xelatex -V geometry:margin=1in -V mainfont="DejaVu Sans"`
2. **VS Code**: Install Markdown PDF extension → right-click → Markdown PDF: Export (PDF)
3. **Python**: Use `markdown` + `weasyprint`:
   ```python
   import markdown
   from weasyprint import HTML
   md = open("docs/PROJECT_ARCHITECTURE.md").read()
   html = markdown.markdown(md, extensions=['tables', 'fenced_code'])
   HTML(string=f"<pre>{html}</pre>").write_pdf("docs/PROJECT_ARCHITECTURE.pdf")
   ```
4. **GitHub**: View on GitHub → Print → Save as PDF (limited formatting)

### 13.6 Git Protocol

- User has authorized commits for this work
- Commit after every completed step
- Style: `feat(academy): ...` / `test(academy): ...` / `docs: ...`
- NEVER `git add -A` blindly; stage only files touched
- NEVER commit `.db` files, `__pycache__`, or `.venv*`

### 13.7 Reference Packs

- **Primary reference**: `capabilities/restaurant/` — THE pattern. Copy its shape, never invent a new one.
- **Sports academy pack**: Built per the reference pattern in S0-S7, fully tested (44 tests), complete with cockpit views, runtime, governance invariants.

---

*End of document. Generated 2026-09-21. Based on repository state at commit 2c7ecd1.*
