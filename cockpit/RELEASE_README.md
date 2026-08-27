# Helix Prime Cockpit v0.1.0

This release packages the Helix Prime Operations Cockpit as a local Windows source release. It includes the Cockpit source, pinned Python dependencies, and `cockpit/start.ps1`, which creates the virtual environment, installs dependencies, and launches Streamlit.

## Requirements

- Windows PowerShell
- Python 3.13+
- Optional: Ollama for local model inference

## Run

Extract the release ZIP, open PowerShell in the extracted folder, and run:

```powershell
.\cockpit\start.ps1
```

The dashboard opens at `http://127.0.0.1:8501`.

## Security & Scope

This is a personal-use local tool intended to run on localhost only. It is not hardened for network exposure or multi-user access and has no authentication layer. Do not deploy it on a shared or public server. The launcher explicitly binds Streamlit to `127.0.0.1`.

## Honest status

Helix Prime remains alpha. This release does not claim client deployments, production enterprise usage, or full agent inter-communication proven through the live UI. Automated test coverage and CI polish remain ongoing work.

## Included project areas

- Streamlit Operations Cockpit
- Six business engines: WFM/Erlang C, RTA, CX Churn Sentinel, B2B Onboarding, Personnel, and CRM
- Four AI agents: SAMI, SUBY, PHILI, and WILI
- Content-based orchestration
- Local Ollama model connection
