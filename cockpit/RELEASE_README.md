# Helix Prime Cockpit v0.1.0

This release packages the Helix Prime Operations Cockpit for local Windows use. It includes the cockpit source, pinned Python dependencies, and `cockpit/start.ps1` which creates the virtual environment, installs dependencies, and launches Streamlit.

## Requirements

- Windows PowerShell
- Python 3.11+
- Optional: Ollama for local model inference

## Run

Extract the release ZIP, open PowerShell in the extracted folder, and run:

```powershell
.\cockpit\start.ps1
```

The dashboard opens at `http://127.0.0.1:8501`.

## Security & Scope

This is a personal-use local tool. It runs on localhost only, is not hardened for network exposure or multi-user access, and has no authentication layer. Do not deploy it on a shared or public server. The launcher explicitly binds Streamlit to `127.0.0.1`.

## Honest status

Helix Prime remains alpha. This release does not claim client deployments, production enterprise usage, or full agent inter-communication proven through the live UI. Test coverage is at 445 passing tests; CI polish is ongoing.

## Included project areas

- Streamlit Operations Cockpit
- Six business engines: WFM/Erlang C, RTA, CX Churn Sentinel, B2B Onboarding, Personnel, and CRM
- Nine AI agents: SAMI, SUBY, PHILI, WILI, ANDY, NONO, MAYA, LIZA, and TOMY
- Content-based orchestration
- Local Ollama model connection
