# Helix Prime

Helix Prime is a unified operations system with six business engines, nine AI agents, a content-based orchestrator, and a Streamlit Operations Cockpit. The agents connect to a local Ollama model.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE.md)
[![Status: Alpha](https://img.shields.io/badge/status-alpha-orange.svg)](ROADMAP.md)

## Current status

Helix Prime is **alpha**. The repository is public and real. The Operations Cockpit is fully functional and can be launched locally. The six business engines, nine AI agents, and content-based orchestrator are implemented. Full agent inter-communication through the live UI is still pending.

There are no client deployments or production enterprise deployments to claim.

## Quick Start (Windows)

### Option 1: One-click setup

```batch
setup.bat
```

Then launch:

```batch
launch.bat
```

### Option 2: Manual setup

```bash
python -m venv .venv
.venv\Scripts\activate     # Windows
pip install -r cockpit/requirements.txt
python launch.py
```

On macOS or Linux, use the provided setup script (requires Python 3.11+):

```bash
./setup.sh
```

Or manually:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r cockpit/requirements.txt
python launch.py
```

The cockpit opens at **http://127.0.0.1:8501**.

### Optional: AI Agents

For full agent functionality, install [Ollama](https://ollama.com) and pull a model:

```bash
ollama pull qwen2.5:1.5b
```

The cockpit works without Ollama — agents show as "Offline" but all other features are available.

## What is included

- **Operations Cockpit:** Streamlit dashboard with dark theme, real-time monitoring, and agent interface.
- **Six business engines:** WFM/Erlang C, RTA, CX Churn Sentinel, B2B Onboarding, Personnel, and CRM.
- **Nine AI agents:** SAMI, SUBY, PHILI, WILI, ANDY (Compliance & Quality), NONO (Fraud), MAYA (Marketing), LIZA (Sales), TOMY (ICT).
- **Content-based routing:** the orchestrator routes requests based on their content.
- **Local model connection:** the agents connect to Ollama when available.

## Tech stack

- Python 3.11+
- Streamlit Operations Cockpit
- Six domain-specific business engines
- Four-agent framework with Ollama integration
- Content-based orchestration
- Pre-commit linting with Ruff

## Repository layout

```text
cockpit/                    Streamlit Operations Cockpit (start here)
app/command_center/agents/  SAMI, SUBY, PHILI, WILI, ANDY, NONO, MAYA, LIZA, TOMY
engines/                    WFM, RTA, CX, B2B, Personnel, and CRM
orchestration/              Content-based request routing
api/                        API layer
marketing/                  Project pages and assets
```

## Verification status

- Operations Cockpit: verified launchable and functional
- Six engines: implemented with individual READMEs
- Nine agents: implemented with base agent framework
- Orchestrator: content-based routing implemented
- Full live-UI agent inter-communication: pending
- Controlled pilot readiness: verified via deterministic dry-run (CONTROLLED_PILOT_READY)
- Release gates: 14/14 pass for controlled_pilot and production_candidate profiles; production profile fails closed on 9 production-only gates requiring external evidence

Part of a larger body of work — see [Hatem Shalaby's profile](https://github.com/HatemIsmailShalaby1979) for the full story.
