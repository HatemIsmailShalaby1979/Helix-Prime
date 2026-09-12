# Helix Prime — Workspace Map

```
Project Helix Prime/
├── cockpit/                  # Operations Control Room
│   ├── cockpit.py            # Main Streamlit Ops Control Room (6 pages)
│   ├── start.ps1             # Launch script
│   ├── __init__.py
│   ├── test_upgrade.py       # Upgrade verification tests
│   └── memory/               # Cognitive Memory Log storage
│       ├── cognitive_log.py  # JSONL + SQLite append-only interaction log
│       ├── cognitive_log.jsonl
│       └── cognitive_log.sqlite
├── GOVERNANCE/               # Logs & maps (you are here)
│   ├── CHANGE_LOG.md
│   ├── WORKSPACE_MAP.md
│   ├── governance_check.py   # Hard-blocking governance enforcement
│   ├── .governance_state.json # Session state tracker
│   └── audit-log/             # Ground truth audit reports (Markdown)
├── engines/                  # Business engine source code
│   ├── b2b/src/main.py
│   ├── crm/src/sales_pipeline.py
│   ├── cx/src/risk_scorer.py
│   ├── personnel/src/main.py
│   ├── rta/src/app.py
│   └── wfm/src/app_wfm.py
├── app/
│   └── command_center/agents/
│       ├── base_agent.py     # BaseAgent with AgentRegistry, inter-agent calling, reasoning traces
│       ├── sami.py           # SAMI agent (CEO/Strategist) — thin wrapper on BaseAgent
│       ├── suby.py           # SUBY agent (Operations Executive) — thin wrapper on BaseAgent
│       ├── phili.py          # PHILI agent (Personnel Director) — thin wrapper on BaseAgent
│       └── wili.py           # WILI agent (L&D Director) — thin wrapper on BaseAgent
├── orchestration/            # Agent-engine coordination
│   ├── orchestrator.py       # Orchestrator with routing rules + lazy agent loading
│   └── __init__.py
├── memory/                   # Metacognitive memory (JSON + ChromaDB)
├── config/                   # Configuration files
├── api/                      # API surface
├── deploy/                   # Deployment scripts
├── docs/                     # Documentation
├── scripts/                  # Utility scripts
├── marketing/                # Marketing assets
├── .opencode/                # AI agent config
├── .venv/                    # Python virtual environment
└── .vscode/                  # VS Code settings
```

## Component Status (2026-07-30 17:00 — Module Force-Reload Fix Applied)

| Component | Status | Notes |
|-----------|--------|-------|
| Ops Control Room | ✅ Running | Streamlit on :8501 (6 pages) — module force-reload on hot-restart to prevent stale cache |
| WFM Engine | ✅ Loaded | engines/wfm/src/app_wfm.py (576 lines) |
| RTA Engine | ✅ Loaded | engines/rta/src/app.py (241 lines) |
| CX Engine | ✅ Loaded | engines/cx/src/risk_scorer.py (564 lines) |
| B2B Engine | ✅ Loaded | engines/b2b/src/main.py (306 lines) |
| Personnel Engine | ✅ Loaded | engines/personnel/src/main.py (466 lines) |
| CRM Engine | ✅ Loaded | engines/crm/src/sales_pipeline.py (576 lines) |
| SAMI Agent | ✅ Loaded | BaseAgent — qwen3:8b, inter-agent calling, recursion depth tracking |
| SUBY Agent | ✅ Loaded | BaseAgent — qwen3:8b, inter-agent calling, recursion depth tracking |
| PHILI Agent | ✅ Loaded | BaseAgent — qwen3:8b, inter-agent calling, recursion depth tracking |
| WILI Agent | ✅ Loaded | BaseAgent — qwen3:8b, inter-agent calling, recursion depth tracking |
| Orchestrator | ✅ Present | orchestration/orchestrator.py |
| Cognitive Memory | ✅ Active | cockpit/memory/cognitive_log.py (JSONL + SQLite) |
| Client Simulation | ✅ Active | 5-step scenario walkthrough in Cockpit |

---

## Wayfinder — Codex Upgrade Tracker

> Merged from `GOVERNANCE/wayfinder/map.md` on 2026-09-12 (single workspace-map
> policy). Ticket list lives in `GOVERNANCE/wayfinder/tickets/`.

### Destination

Helix Prime Codex: a human-supervised, enterprise-grade AI organization (8 GMs + SAMI CEO + 6 engines + workflow control plane) proven by one complete contact-centre vertical slice (WFM → RTA → OPS → Compliance → HR/L&D → CRM/CX → SAMI summary) that runs with durable workflows, typed contracts, approvals, audit evidence, tenant isolation, and failure-injection verification. Codex name claimed after C0–C5; production-ready only after C8 evidence pack.

### Notes

- Domain: contact-centre & business operations AI org; local-first (Ollama+SQLite) → replaceable storage.
- Every session: read `docs/HELIX_CODEX_OS_MASTER_BLUEPRINT.md` (the current execution blueprint),
  `GOVERNANCE/capability-matrix.json`, `GOVERNANCE/RELEASE_LABELS.md`.
- Skills to use: `domain-modeling` + `grilling` for GM boundaries, `tdd` for contracts, `diagnosing-bugs` for workflow runtime, `research` for sibling integration.
- Non-negotiables: Expand not erase; human approval for irreversible actions; every action typed/attributable; fail-closed; one source of truth; evidence before status.
- Tracker: local-markdown (`GOVERNANCE/wayfinder/tickets/*.md` linked from this map). Each ticket filename is its id; priority = label; blocking wired via `Blocks:`/`BlockedBy:` front-matter. Frontier = open tickets with no open blockers.
- Label `wayfinder:map` on this file; tickets carry `wayfinder:<type>`.

### Decisions so far

- [C0 Truth Lock — Capability Matrix + Hygiene + Smoke](wayfinder/tickets/C0-truth-lock.md) — Closed 2026-08-27
- [C1 Organization Model & Typed Contracts](wayfinder/tickets/C1-organization-contracts.md) — Closed 2026-08-27
- [C1a Capability-Based Discovery](wayfinder/tickets/C1a-capability-discovery.md) — Closed 2026-08-27
- [C2 Control Plane and Workflow Runtime](wayfinder/tickets/C2-control-plane.md) — Closed 2026-08-27
- [C3 Security, Data Governance and Observability](wayfinder/tickets/C3-security-observability.md) — Closed 2026-08-27
- [C4 Six-Engine Productization](wayfinder/tickets/C4-engine-productization.md) — Closed 2026-08-27
- [C6 GM Expansion](wayfinder/tickets/C6-gm-expansion.md) — Closed 2026-08-28
- [C7 Sibling-Project Integration](wayfinder/tickets/C7-sibling-integration.md) — Closed 2026-08-28
- [C8 Production Candidate & Controlled Pilot Pack](wayfinder/tickets/C8-production-pack.md) — Closed 2026-08-28

### Not yet specified

- Network/deployed integration transport (HTTP/gRPC/message bus) for siblings — local-first (in-memory/file) deferred to C8 roadmap; L&D Command Center Windows build pending on sibling side.
- Deployment profiles (local single-node, private-network pilot, optional cloud) — build/migration/rollback evidence needed at C8.

### Out of scope

- Branding / dashboards beyond one verified contact-centre slice (per sprint backlog note).
- Patent / blockchain / quantum claims (explicitly excluded in ROADMAP).
- Full cloud hosting or client deployments before C8 gate.
- Rewriting 2-commit public git history with `push --force` without owner approval (see `GIT_HISTORY_RECONCILIATION.md`).
