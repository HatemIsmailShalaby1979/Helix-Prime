![CI](https://github.com/HatemIsmailShalaby1979/Helix-Prime/actions/workflows/python-app.yml/badge.svg)
![License](https://img.shields.io/github/license/HatemIsmailShalaby1979/Helix-Prime)
![Release](https://img.shields.io/github/v/release/HatemIsmailShalaby1979/Helix-Prime)

# Helix Prime

> **The operations core of Helix Codex.**

Helix Prime is a local-first platform that runs six business engines (WFM, RTA, CX, B2B, Personnel, CRM) with nine AI agents routing requests by content. It includes a Streamlit cockpit, governed memory, and evidence-based approval workflows — all running on your machine with no cloud dependency.

This is the first product for **Helix Codex**: an accountable AI operating organization that helps businesses understand operations, coordinate decisions, and improve through evidence without silently taking control.

## Where it stands

- **Controlled-pilot ready:** `CONTROLLED_PILOT_READY`
- **Production:** NOT_READY — no external evidence or human approvals exist
- **445 tests passing** across contracts, control plane, security, engines, integrations, pilot, memory, metacognition, and capability packs
- Governance checker: **PASS**
- Synthetic call-centre and restaurant demonstrations: verified
- Live connectors and external writes: intentionally disabled

## What's inside

- Six engines: WFM (Erlang C), RTA, CX Churn Sentinel, B2B Onboarding, Personnel, CRM
- Nine agents (SAMI, SUBY, PHILI, WILI, ANDY, NONO, MAYA, LIZA, TOMY) with content-based routing
- Tenant identity and deny-by-default authorization
- Workflow state machine with approvals, retries, and dead-letter handling
- Read-only boundaries for Zendesk, Salesforce, and Clay
- Evidence-backed account-health diagnosis
- Provenance-bearing command center
- Tenant-isolated governed memory with retention
- Evidence-gated improvement proposals that never self-deploy
- Local adapters with cloud-ready interfaces

## The proving workflow

Account context + support history + enrichment + operational signals

→ account-health diagnosis
→ evidence and risk explanation
→ next-best-action recommendation
→ cross-role approval preview
→ outcome recorded in governed memory

The current demo uses synthetic and consented-historical data only. This is not a claim of production deployment, universal business coverage, or autonomous operation.

## Run it

### Windows

1. Install Python 3.11+ from [python.org](https://www.python.org/downloads/windows/).
2. Download the source ZIP and extract it.
3. Open Command Prompt in the extracted folder.
4. Run `setup.bat`.
5. Run `launch.bat`.

### Linux

```bash
sudo apt-get update
sudo apt-get install -y python3 python3-venv
python3 -m venv .venv
source .venv/bin/activate
pip install -r cockpit/requirements.txt
python launch.py
```

Ollama is optional. Without it, the system runs in deterministic offline mode and reports the limitation clearly.

## Why this exists

I spent 28 years in operations hitting the same walls: manual forecasting, fragmented tools, reactive firefighting. I built Helix Prime to solve those problems — and to prove that operational intelligence can be governed, not autonomous. Decisions have owners. Recommendations expose evidence. Actions have authority boundaries. Memory carries provenance. Improvement requires evaluation, review, approval, and rollback.

## Next milestone

A real design-partner pilot. Read-only first, minimum data, explicit consent, measured baseline. No production claim until the production gates pass.

## Related

- [Helix Education](https://github.com/HatemIsmailShalaby1979/Helix-Education)
- [Study Studio](https://github.com/HatemIsmailShalaby1979/Study-Studio)
- [L&D Command Center](https://github.com/HatemIsmailShalaby1979/L-D-Command-Center)
- [Hatem Shalaby portfolio](https://github.com/HatemIsmailShalaby1979)

## Author

**Hatem Ismail Shalaby** — Operations Architect and AI Systems Engineer

## License

MIT
