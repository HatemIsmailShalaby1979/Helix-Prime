> **Status: Private / Pre-pilot / 1,758 tests passed / 0 failed (snapshot 2026-09-24) / Production NOT_READY / Container never built / No external audit / No release tag.**
>
> Internal self-approval only (`approver: "operator-pilot-consent"`). No third-party sign-off exists.

# Helix Prime

> **The operations core of Helix Codex.**

> **Authority chain:** `00_CONSTITUTION.md` (authority) → `docs/HELIX_CODEX_OS_MASTER_BLUEPRINT.md` (architecture + commercial record) → implementation. On conflict, the earlier link in the chain wins. The constitution outranks the blueprint, and both outrank status summaries, roadmaps, and release docs.

Helix Prime is a local-first platform that runs six business engines (WFM, RTA, CX, B2B, Personnel, CRM) with nine AI agents routing requests by content. The canonical artifact is **`helix-api`**, a governed FastAPI spine where identity, RBAC, approvals, the kill switch, metrics, and the audit chain are enforced. The Streamlit cockpit is a secondary read-only diagnostic surface. Everything runs on your machine with no cloud dependency.

Helix Prime is the operations core of **Helix Codex**, an accountable AI operating organization that helps businesses understand operations, coordinate decisions, and improve through evidence without silently taking control.

## Where it stands

**Release-candidate track (2026-09-24):** stabilization is centered on the governed `helix-api` controlled-pilot surface. The boundary is one tenant, synthetic or explicitly consented data, read-only integrations, human approval, and independent peer review. This is not a production claim.

| Check | Result | Snapshot |
|---|---|---|
| Full test suite | 1,758 passed / 0 failed / 0 skipped, one process | 2026-09-24 |
| Lint / format / mypy / bandit / pip-audit | Clean | 2026-09-24 |
| Dependency / migration drift | Green | 2026-09-24 |
| Governance checker | PASS | 2026-09-24 |
| Release gate `app_pilot` | `CONTROLLED_PILOT_READY` (exit 0) | 2026-09-24 |
| Release gate `controlled_pilot` | `CONTROLLED_PILOT_READY` (exit 0) | 2026-09-24 |
| Release gate `production_candidate` | `PRODUCTION_CANDIDATE` (exit 0) | 2026-09-24 |
| Release gate `production` | `NOT_READY` (exit 1) | 2026-09-24 |
| Evidence directories | 714 release dirs under `evidence/releases/` | 2026-08-28 → 2026-09-15 |

- **Repo status:** Private repository on `main`; verify the exact candidate SHA and remote position with `git rev-parse HEAD` and `git ls-remote`.
- **Controlled-pilot ready:** `CONTROLLED_PILOT_READY` is an internal self-approval (`approver: "operator-pilot-consent"`), not a third-party sign-off. There is no external pilot.
- **Production:** `NOT_READY`. The nine red gates are production-only and red by design: `signed_production_evidence`, `certified_data_isolation`, `external_observer_audit`, `production_deployment_architecture`, `disaster_recovery_evidence`, `operational_ownership`, `incident_oncall_ownership`, `security_review`, `legal_privacy_review`.
- **Verification:** candidate status is valid only for commands run against the exact candidate commit. Use `.github/copilot-instructions.md` for the canonical command inventory.
- **Evidence character:** the 714 release directories span 2026-08-28 to 2026-09-15 and come from one burst of harness runs in a single session (03:18–05:47 UTC). That is not a multi-day production track record.
- **Synthetic demonstrations** (call-centre, restaurant, sports academy): verified against synthetic or consented-historical data only.
- **Live connectors and external writes:** intentionally disabled.
- **Container image:** CI must build and readiness-smoke-test the API image before candidate promotion. Local Docker availability is not assumed, and the image has not been built.

Test counts move as the suite grows. `MASTER_STORY.md` is the authority on the verified state and records 445 tests as of 2026-08-29. The 1,758 figure above is the 2026-09-24 snapshot. The release candidate must be re-measured before any release.

> Nothing in this README is a production claim. The system is internally governed, self-tested, and pre-pilot, with no real client and no external approval. See `MASTER_STORY.md` for the full verified account.

## What's inside

- Six engines: WFM (Erlang C), RTA, CX Churn Sentinel, B2B Onboarding, Personnel, CRM
- Nine agents (SAMI, SUBY, PHILI, WILI, ANDY, NONO, MAYA, LIZA, TOMY) with content-based routing
- **Two vertical capability packs**: `capabilities/restaurant/` (the reference pattern) and `capabilities/sports_academy/` (first real vertical, built for Scoach Academy Hub)
- **Helix Codex App** (`helix_codex_app/`) — the daily-use product layer: identity, chat, documents, tasks, calendar, attendance, governed memory, and a low-code capability loader
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

The **one** deployable artifact is the governed FastAPI service spine. Identity, RBAC, approvals, the kill switch, metrics, and the audit chain are enforced behind this surface. It runs with bare `uvicorn` semantics and no UI dependency:

```bash
pip install 'helix-codex-os[web]'        # or `pip install -r requirements.txt`
helix-api                                # binds 127.0.0.1:8000 by default
```

Settings come from `HELIX_*` environment variables (see `server/config.py`). `HELIX_HOST=127.0.0.1` and `HELIX_PORT=8000` are the defaults, and the API refuses to boot in `HELIX_PROFILE=production` without the external gate inputs. `helix-api` is the same entry point the Docker profile runs.

### Secondary: the cockpit dashboard (`helix-cockpit`)

The Streamlit dashboard is a **read-only, secondary diagnostic surface**, not the deployable artifact. It is equivalent to `python launch.py`:

```bash
helix-cockpit                            # binds 127.0.0.1:8501
```

### Legacy / do not build on these

- `python launch.py` / `launch.bat` — the Streamlit launcher; superseded by `helix-cockpit`.
- `python desktop.py` — pywebview desktop shell; the packaged wheel does not ship a desktop UI and no console script exposes it.
- `infra/docker/docker-compose.yml` — containerized profile running the same `helix-api` plus the cockpit and an Ollama sidecar; it is a deployment profile, not a separate application surface.

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

## Honest boundary

Helix Prime is a private, pre-pilot system. It has no external pilot, no production deployment, and no paying client.

- No external audit and no certification.
- No certified data isolation.
- No signed security review.
- No legal privacy review.
- No assigned on-call owner; the operator is one person.
- The container image has never been built.
- Live connectors and external writes are intentionally disabled.
- No revenue has been realised.

## Next milestone

A real design-partner pilot. Read-only first, minimum data, explicit consent, measured baseline. No production claim until the production gates pass.

## The founder's story

I spent twenty-eight years in contact-centre operations and workforce management. Forecasting, scheduling, adherence, service levels, churn. The same problems appeared in every company I worked in, and none of the tools solved them properly.

In April 2026 I left that career and started building full time — alone, and teaching myself to write software as I went. The first four tools were published six weeks later, in May and June 2026. Each one took a single operational problem and solved it properly. They were not impressive. They were correct.

Those four tools converged into one idea: **Helix Codex**, an accountable AI operating organization. Not an autonomous agent. An organization with a constitution, named roles with bounded authority, evidence trails, and a human at every consequential boundary. Helix Prime is its operations core.

Helix Prime is the operations core of Helix Codex — the platform the rest of the
work is built on. It is maintained by one person, with no team and no funding. It
has not been externally audited and it has not made revenue. Where it is
unfinished, this document says so.

## Related work

- [Helix Education](https://github.com/HatemIsmailShalaby1979/Helix-Education) — event-sourced learning engine
- [Study Studio](https://github.com/HatemIsmailShalaby1979/Study-Studio) — local-first AI tutor
- [L&D Command Center](https://github.com/HatemIsmailShalaby1979/L-D-Command-Center) — desktop learning and career workstation
- [Blue Waves](https://github.com/HatemIsmailShalaby1979/Blue-Waves-) — content studio
- [LIVE Support Assistant](https://github.com/HatemIsmailShalaby1979/LIVE-Support-Assistant) — explainable support prototype
- [Full portfolio](https://github.com/HatemIsmailShalaby1979) — the front door

### The 2026 building attempts

- [WFM Forecasting Calculator](https://github.com/HatemIsmailShalaby1979/wfm-forecasting-calculator)
- [RTA Command Center](https://github.com/HatemIsmailShalaby1979/RTA_command_center)
- [CX Sentiment Sentinel](https://github.com/HatemIsmailShalaby1979/cx-sentiment-sentinel)
- [Dynamic Ops Automation Engine](https://github.com/HatemIsmailShalaby1979/Dynamic-Ops-Automation-Engine)

## Author

**Hatem Ismail Shalaby** — Operations Architect · AI Systems Engineer · Founder

- GitHub: [HatemIsmailShalaby1979](https://github.com/HatemIsmailShalaby1979)
- LinkedIn: [hatem-shalaby-202902127](https://www.linkedin.com/in/hatem-shalaby-202902127/)
- Email: hatemshalaby2025@gmail.com

Based in Al Obour City, Al-Qalyubia Governorate, Egypt.

## Licence

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
