# Helix Prime

Helix Prime is a unified operations system with six business engines, four AI agents, a content-based orchestrator, and a Streamlit Operations Cockpit. The agents connect to a local Ollama model.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE.md)
[![Status: Alpha](https://img.shields.io/badge/status-alpha-orange.svg)](ROADMAP.md)

## Current status

Helix Prime is **alpha**. The repository is public and real. Core modules, the agents, the engines, the orchestrator, and the Operations Cockpit are present. Full agent inter-communication through the live UI is still pending, as are incremental improvements to automated test coverage and CI polish.

There are no client deployments or production enterprise deployments to claim.

## What is included

- **Six business engines:** WFM/Erlang C, RTA, CX Churn Sentinel, B2B Onboarding, Personnel, and CRM.
- **Four AI agents:** SAMI, SUBY, PHILI, and WILI.
- **Content-based routing:** the orchestrator routes requests based on their content.
- **Operations Cockpit:** a Streamlit interface for the system.
- **Local model connection:** the agents connect to Ollama.
- **CI:** the repository has a live CI pipeline with pre-commit linting.

## Tech stack

- Local Ollama model connection
- Streamlit Operations Cockpit
- Six domain-specific business engines
- Four-agent framework
- Content-based orchestration
- CI with pre-commit linting

## Setup

### Prerequisites

- Python 3.13+
- Optional: Ollama for local model inference

### Run the Operations Cockpit

```bash
python -m venv .venv
.venv\Scripts\activate     # Windows
pip install -r cockpit/requirements.txt
python launch.py --dash-only
```

The dashboard is available at `http://localhost:8501`.

On macOS or Linux, activate the environment with `source .venv/bin/activate`.

## Repository layout

```text
app/command_center/agents/  SAMI, SUBY, PHILI, and WILI
engines/                    WFM, RTA, CX, B2B, Personnel, and CRM
orchestration/              Content-based request routing
cockpit/                    Streamlit Operations Cockpit
api/                        API layer
marketing/                  Project pages and assets
```

## Verification status

The repository is alpha. The full live-UI proof of agent inter-communication is pending, and automated test coverage and CI polish remain ongoing work.

Part of a larger body of work — see [Hatem Shalaby's profile](https://github.com/HatemShelby) for the full story.
