# Helix Prime

> **The governed operations core of Helix Codex.**

Helix Prime is a local-first operations platform that brings business engines, governed AI roles, workflow orchestration, evidence, memory, approvals, and a command-center cockpit into one system.

It is the first proving product for **Helix Codex**: an accountable AI operating organization designed to help businesses understand operations, coordinate decisions, and improve through evidence without silently taking control.

## Verified Phase 1 status

- **Controlled-pilot ready:** CONTROLLED_PILOT_READY
- **Production:** NOT_READY until external evidence and human approvals exist
- **445 tests passing** across contracts, control plane, security, engines, integrations, pilot, memory, metacognition, and capability packs
- Governance checker: **PASS**
- Synthetic call-centre and restaurant demonstrations: verified
- Live connectors and external writes: intentionally disabled

## What is implemented

- Six operational engines: WFM, RTA, CX, B2B onboarding, Personnel, and CRM
- Nine governed AI roles with orchestrator routing
- Tenant/client identity and deny-by-default authorization
- Workflow state machine, idempotency, approvals, retries, and dead-letter handling
- Read-only provider-neutral boundaries for Zendesk, Salesforce, and Clay
- Evidence-backed customer-success account-health diagnosis
- Provenance-bearing command center
- Tenant-isolated governed memory with retention and supersession
- Evidence-gated improvement proposals that never self-deploy
- Local adapters and cloud-ready interfaces without cloud lock-in
- Synthetic controlled-pilot package with read-only period and minimum-data policy

## The proving workflow

Account context + support history + enrichment + operational signals

→ account-health diagnosis
→ evidence and risk explanation
→ next-best-action recommendation
→ cross-role approval preview
→ outcome recorded in governed memory

The current demonstration uses synthetic and consented-historical modes only. It does not claim production deployment, universal business coverage, or autonomous operation.

## Download and run

- [Download current source ZIP](https://github.com/HatemIsmailShalaby1979/Helix-Prime/archive/refs/heads/main.zip)
- [View releases](https://github.com/HatemIsmailShalaby1979/Helix-Prime/releases)

### Windows

1. Install Python 3.11 or newer from [python.org](https://www.python.org/downloads/windows/).
2. Download and extract the current source ZIP.
3. Open Command Prompt in the extracted folder.
4. Run setup.bat.
5. Run launch.bat.

### Linux

    sudo apt-get update
    sudo apt-get install -y python3 python3-venv
    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r cockpit/requirements.txt
    python launch.py

Ollama is optional. Without it, the system uses a deterministic offline mode and clearly reports that limitation.

## Why Helix Prime matters

It is an experiment in **governable organizational intelligence**: decisions have owners, recommendations expose evidence, actions have authority boundaries, memory carries provenance, and improvement requires evaluation, review, approval, and rollback.

## Next evidence milestone

A real design-partner pilot: read-only first, minimum data, explicit consent, measured baseline, and no production claim until the production gates pass.

## Related projects

- [Helix Education](https://github.com/HatemIsmailShalaby1979/Helix-Education)
- [Study Studio](https://github.com/HatemIsmailShalaby1979/Study-Studio)
- [L&D Command Center](https://github.com/HatemIsmailShalaby1979/L-D-Command-Center)
- [Hatem Shalaby portfolio](https://github.com/HatemIsmailShalaby1979)

## Author

**Hatem Ismail Shalaby** — Operations Architect and AI Systems Engineer

## License

MIT
