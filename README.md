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
- **Verification:** C0 dependency drift check passes; C4 adapter, C5 seam, C6 activation and C7 event-contract smoke paths pass. The full historical suite remains subject to legacy teardown migration.
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
- Append-only, hash-chained `audit_events` ledger and exportable governance evidence pack
- Versioned sibling-service event contracts with no cross-repository imports
- SQL-bound tenant-scoped storage and local-first Docker deployment profile

## The proving workflow

Account context + support history + enrichment + operational signals

→ account-health diagnosis
→ evidence and risk explanation
→ next-best-action recommendation
→ cross-role approval preview
→ outcome recorded in governed memory

The current demo uses synthetic and consented-historical data only. This is not a claim of production deployment, universal business coverage, or autonomous operation.

## Run it

### Canonical: the API spine (`helix-api`)

The **one** deployable artifact is the governed FastAPI service spine. It is
where identity, RBAC, approvals, kill switch, metrics and the audit chain are
enforced — everything the platform claims to be happens behind this surface.
It runs with bare `uvicorn` semantics and no UI dependency:

```bash
pip install 'helix-codex-os[web]'        # or `pip install -r requirements.txt`
helix-api                                # binds 127.0.0.1:8000 by default
```

Settings come from `HELIX_*` environment variables (see `server/config.py`);
`HELIX_HOST=127.0.0.1` / `HELIX_PORT=8000` are the defaults, and the API
refuses to boot in `HELIX_PROFILE=production` without the external gate
inputs. `helix-api` is the same entry point the Docker profile runs.

### Secondary: the cockpit dashboard (`helix-cockpit`)

The Streamlit dashboard is a **read-only, secondary diagnostic surface**, not
the deployable artifact. It is equivalent to `python launch.py`:

```bash
helix-cockpit                            # binds 127.0.0.1:8501
```

### Legacy / do not build on these

- `python launch.py` / `launch.bat` — the Streamlit launcher; superseded by
  `helix-cockpit`.
- `python desktop.py` — pywebview desktop shell; the packaged wheel does not
  ship a desktop UI and no console script exposes it.
- `infra/docker/docker-compose.yml` — containerized profile running the same
  `helix-api` plus the cockpit and an Ollama sidecar; it is a deployment
  profile, not a separate application surface.

### Windows (source checkout)

1. Install Python 3.12+ from [python.org](https://www.python.org/downloads/windows/).
2. Download the source ZIP and extract it.
3. Open Command Prompt in the extracted folder.
4. Run `setup.bat`.
5. Run `helix-api` (or `python -m server.cli`).

### Linux (source checkout)

```bash
sudo apt-get update
sudo apt-get install -y python3 python3-venv
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
helix-api   # or: python -m server.cli
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

<!-- HELIX_ROLE_MATRIX:START -->
## Canonical RoleSpec matrix (generated)

This block is generated from `control_plane/governance.py`. Role IDs,
engine ownership, data classifications, approval limits and KPIs below
are structural facts; surrounding prose must not contradict them.

| RoleSpec ID | Engines | Classifications | Financial limit (USD) | KPIs | Oversight only |
|---|---|---|---:|---|---|
| `sami` | wfm, rta, cx, crm, b2b, personnel, control_plane | public, internal, client_confidential, personnel_sensitive, financial, regulated_high_risk | unlimited (human escalation) | system_health, operational_margin | False |
| `ops_gm` | wfm, rta, cx | internal, client_confidential | 500.00 | sla, service_level, occupancy, adherence, aht | False |
| `compliance_quality_gm` | none | public, internal, client_confidential, personnel_sensitive, financial, regulated_high_risk | 0.00 | quality_score, compliance_drift | True |
| `fraud_revenue_gm` | crm, b2b | internal, client_confidential, financial | 0.00 | leakage, anomaly_delta | False |
| `hr_personnel_gm` | personnel, wfm | internal, personnel_sensitive | 1000.00 | turnover_rate, time_to_hire | False |
| `ld_gm` | wfm | internal, personnel_sensitive | 200.00 | competency_score, time_to_competency | False |
| `sales_gm` | crm, b2b | internal, client_confidential | 2500.00 | pipeline_value, win_rate | False |
| `marketing_gm` | crm | public, internal | 500.00 | cac, lead_volume | False |
| `ict_gm` | control_plane | internal, regulated_high_risk | 5000.00 | engine_latency, model_timeout | False |

### Runtime aliases

| Alias | Canonical role / engine |
|---|---|
| `SAMI` / `sami` | `sami` |
| `SUBY` / `suby` | `ops_gm` |
| `PHILI` / `phili` | `hr_personnel_gm` |
| `WILI` / `wili` | `ld_gm` |
| `NONO` / `nono` | `fraud_revenue_gm` |
| `fraud_gm` (YAML compatibility alias) | `fraud_revenue_gm` |

### Limitations

- `None` financial limit does not mean autonomous unlimited approval; SAMI remains human-escalated.
- `oversight_only=True` means the role proposes/reviews and does not execute an engine.
- Unknown role, engine, classification or alias fails closed.
- This matrix is not a production certification or customer deployment claim.
<!-- HELIX_ROLE_MATRIX:END -->
