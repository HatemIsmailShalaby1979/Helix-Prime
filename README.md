> **Status: Private / Pre-pilot / 1,758 passed / 0 failed / Container never built / No external audit / No release tag.**
>
> Internal self-approval only (`approver: "operator-pilot-consent"`). No third-party sign-off exists.

# Helix Prime

> **The operations core of Helix Codex.**

> **Authority chain:** `00_CONSTITUTION.md` (authority) → `docs/HELIX_CODEX_OS_MASTER_BLUEPRINT.md` (architecture + commercial record) → implementation. On conflict, the earlier link in the chain wins — the constitution outranks the blueprint, and both outrank status summaries, roadmaps, and release docs.

Helix Prime is a local-first platform that runs six business engines (WFM, RTA, CX, B2B, Personnel, CRM) with nine AI agents routing requests by content. The canonical artifact is **`helix-api`**, a governed FastAPI spine where identity, RBAC, approvals, the kill switch, metrics, and the audit chain are enforced; the Streamlit cockpit is a secondary read-only diagnostic surface. Everything runs on your machine with no cloud dependency.

This is the first product for **Helix Codex**: an accountable AI operating organization that helps businesses understand operations, coordinate decisions, and improve through evidence without silently taking control.

## Why this exists (human note)

I did not build Helix Prime to impress an interviewer with the word "revolutionize." I built it because I switched careers, started learning alone, and decided that when crisis hits — when operations break, when data is missing, when decisions need to be made fast — the answer should not be a black box. It should be a governed system that tells you exactly what it knows, exactly what it doesn't, and exactly what it needs before it acts.

Helix Codex is the organization I designed for that. Helix Prime is its core engine. It runs locally. It has no cloud dependency. It has nine agents, six engines, a fail-closed kill switch, an audit chain, and a constitution that outranks any summary. It has not been externally audited. It has not made revenue. It is maintained by one engineer, solo, self-taught, with no team, no venture funding, and no hidden claims.

If you want to see the verified state — not the marketing version — read `MASTER_STORY.md` first. It was written by running real commands, not by trusting an agent's summary.

## Where it stands

**Release-candidate track (2026-09-24):** stabilization is centered on the
governed `helix-api` controlled-pilot surface. The boundary is one tenant,
synthetic or explicitly consented data, read-only integrations, human approval,
and independent peer review. This is not a production claim.

- **Repo status:** Private repository on `main`; verify the exact candidate SHA and remote position with `git rev-parse HEAD` and `git ls-remote`.
- **Controlled-pilot ready:** `CONTROLLED_PILOT_READY` — but this is an *internal self-approval* (`approver: "operator-pilot-consent"`), not a third-party sign-off. There is no external pilot.
- **Production:** NOT_READY — no external evidence, no certified isolation, no assigned on-call owner, no signed security review, no legal privacy review, no external observer audit.
- **Verification:** candidate status is valid only for commands run against the exact candidate commit. Use `.github/copilot-instructions.md` for the canonical command inventory.
- Governance checker: **PASS**
- Release gate: `app_pilot` and `controlled_pilot` → `CONTROLLED_PILOT_READY` (exit 0); `production_candidate` → `PRODUCTION_CANDIDATE` (exit 0); `production` → `NOT_READY` (exit 1, 9 external-only gates red by design: signed_production_evidence, certified_data_isolation, external_observer_audit, production_deployment_architecture, disaster_recovery_evidence, operational_ownership, incident_oncall_ownership, security_review, legal_privacy_review).
- Synthetic demonstrations (call-centre, restaurant, sports academy): verified against synthetic/consented-historical data only.
- Live connectors and external writes: intentionally disabled.
- **Container image:** CI must build and readiness-smoke-test the API image before candidate promotion; local Docker availability is not assumed.
- **Evidence:** 714 release directories (`evidence/releases/`) spanning 2026-08-28 to 2026-09-15 — one burst of harness runs in a single session (03:18–05:47 UTC), not a multi-day production track record.

> Nothing in this README is a production claim. The system is internally governed, self-tested, pre-pilot, with no real client and no external approval. See `MASTER_STORY.md` for the full verified account.

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
