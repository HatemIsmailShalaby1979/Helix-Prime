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
