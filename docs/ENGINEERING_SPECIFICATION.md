# Helix Prime — Engineering Specification

> **Audience:** Senior developers, engineering reviewers, technical architects.
> **Canonical source of truth:** `MASTER_STORY.md` (workspace root).
> **Constitution 000:** *Architecture serves as the expression of truth. Identity precedes implementation.*
> **Truth note:** Earlier drafts of this document described a two-repository layout
> (`AI OPS Engineering/helix-prime-ecosystem` + `helix-story`) that no longer exists,
> and contained fabricated claims (a "proof ledger" with "57 entries across Client A
> LIVE, VF UK, and Lufthansa"). Those claims are void. Helix Prime is one unified
> repository. There is no proof ledger, no "immutable audit trail," and no customer
> accounts in this codebase. The structure below reflects the repository as it exists.

---

## 1. Repository Architecture

Helix Prime is a **single public repository** (`github.com/HatemShelby/Helix-Prime`) with the following top-level areas:

```
.
├── app/command_center/              # Agent runtime — 4 AI agents (crash-isolated)
│   └── agents/                      #   base_agent.py + sami, suby, phili, wili
├── orchestration/                   # Orchestrator (content-based routing)
│   └── orchestrator.py
├── engines/                         # 6 kebab-case domain engines
│   ├── b2b/                         # B2B Onboarding Automator
│   ├── cx/                          # CX Churn Sentinel
│   ├── crm/                         # CRM Engine (Sales Pipeline + Support)
│   ├── personnel/                   # Personnel Engine (Talent + Workforce Planning)
│   ├── rta/                         # RTA Command Center (Real-Time Adherence)
│   └── wfm/                         # WFM Forecasting (Erlang C + Variance)
├── cockpit/                         # Streamlit Operations Cockpit
│   ├── cockpit.py                   #   Dashboard entry point
│   ├── memory/                      #   Cognitive log (JSONL + SQLite)
│   └── requirements.txt
├── api/                             # TypeScript generation/metrics utilities
├── memory/ 06_memory/               # Cross-cutting memory stores (ChromaDB)
├── marketing/                       # Product marketing — site, demo, scripts
├── docs/                            # Documentation (architecture, operations, archive)
├── tests/                           # Test suite
├── GOVERNANCE/                      # Change log and audit trail
├── launch.py                        # Combined launcher
└── run_tests.ps1                    # Test runner
```

### 1.1 Agent Runtime — `app/command_center/`

Four AI agents, each isolated in its own subprocess so that one failing agent does not take down the system:

- `sami.py` — CEO / strategy
- `suby.py` — operations
- `phili.py` — personnel
- `wili.py` — learning & development

All four connect to a local Ollama model (`HELIX_MODEL_BACKEND` environment → config → safe default). Agents communicate over strict JSON; there is no shared memory between language boundaries.

### 1.2 Orchestration — `orchestration/orchestrator.py`

Routes requests to agents/engines according to content. The mechanism exists and is proven in isolation; **full agent inter-communication through the live UI is still pending** (verified as pending in `MASTER_STORY.md`).

### 1.3 Operations Cockpit — `cockpit/`

Streamlit dashboard exposing the six engines and the cognitive memory log. Launched via `python launch.py --dash-only` and served at `http://localhost:8501`.

### 1.4 Domain Engines — `engines/`

Six consolidated domain engines, each independently runnable with its own `requirements.txt` and README:

| Engine | Purpose | Key files |
|---|---|---|
| `wfm/` | WFM Forecasting — Erlang C, data pipeline, variance | `src/erlang_c.py`, `src/data_pipeline.py`, `src/variance_engine.py` |
| `rta/` | RTA Command Center — adherence calc + visualizations | `src/calculations.py`, `src/visualizations.py`, `src/app.py` |
| `cx/` | CX Churn Sentinel — 4-KPI weighted risk scoring | `src/risk_scorer.py`, `src/kpi_aggregator.py`, `src/alert_dispatcher.py` |
| `b2b/` | B2B Onboarding — SOP generation | `src/automator.py`, `notion_adapter/notion_adapter.py` |
| `personnel/` | Personnel — talent acquisition + workforce planning | `src/talent_acquisition.py`, `src/workforce_planning.py`, `src/pipeline_manager.py` |
| `crm/` | CRM — sales pipeline + customer support SLA | `src/sales_pipeline.py`, `src/customer_support.py` |

## 2. Security Posture

- **No secrets on disk**: no `.env` with real credentials; `.env.example` only.
- **Local-first**: zero mandatory cloud dependency. Data stays on local hardware unless explicitly configured otherwise.
- **Crash isolation**: agents run in isolated subprocesses.
- **No hardcoded configuration**: model selection resolves via environment → config → safe default.

## 3. Data Model

### Cognitive Log (`cockpit/memory/`)

- `cognitive_log.jsonl` — append-only log of cockpit activity
- `cognitive_log.py` — log writer module
- `cognitive_log.sqlite` — SQLite store

### ChromaDB Vector Store (`06_memory/vector_store/`)

Persistent ChromaDB index used by the memory layer.

## 4. API Contracts

### Orchestrator / Agent JSON

```
Request:  {"task": "analyze", "params": {...}, "model": "..."}
Response: {"status": "success", "output": "...", "accomplishment": "..."}
Error:    {"status": "error", "error_type": "...", "message": "..."}
```

## 5. Deployment

### Local Development

```powershell
# Terminal 1 — Operations Cockpit
python launch.py --dash-only
# → http://localhost:8501

# Or directly from cockpit/
streamlit run cockpit/cockpit.py --server.port 8501
```

The `marketing/` folder contains `render.yaml`, `azure.yaml`, `Dockerfile`, and
`infra/main.bicep` as **deployment scaffolding for the marketing site**. None of these
is evidence of a hosted production service; there are no client deployments and no
production enterprise usage.

## 6. Test Status

| Area | Status |
|---|---|
| Cockpit client profiles | `tests/test_cockpit_client_profiles.py` |
| API utilities | `api/*.test.ts`, `verify-generate.js` |
| Automated coverage | Ongoing work — not yet comprehensive |

## 7. Known Gaps (verified)

- Full agent inter-communication proven through the live UI is **pending**.
- Automated test coverage is **ongoing work**.
- Significant lint/style debt exists in the codebase (non-functional; see `GAP_ANALYSIS.md`).
- No client deployments, no production enterprise usage, no "proof ledger."

---

*Specification maintained by **Hatem Shalaby**. Source of truth: `MASTER_STORY.md`.*
