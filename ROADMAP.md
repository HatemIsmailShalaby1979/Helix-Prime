# Helix Prime — Roadmap

> **Classification:** PROJECT DOCUMENT
> **Rule:** No claim in this document may exceed what is verified in `MASTER_STORY.md`. This roadmap is replaced by this file when the previous draft is found to contradict verified reality. See `CHANGELOG.md` for the audit trail.

---

## Where the project actually stands

Helix Prime is a **solo-built, public alpha** operations system. It is not yet a product, has no customers, and makes no deployment claims.

**What is real today (verified):**

- 6 business engines: WFM/Erlang C, RTA, CX Churn Sentinel, B2B Onboarding, Personnel, CRM
- 9 AI agents: SAMI, SUBY, PHILI, WILI, ANDY (Compliance & Quality), NONO (Fraud), MAYA (Marketing), LIZA (Sales), TOMY (ICT), connected to a local Ollama model
- An orchestrator with content-based request routing
- A Streamlit Operations Cockpit (dashboard)
- A public repository at `github.com/HatemShelby/Helix-Prime`
- CI pipeline live with pre-commit linting

**What is explicitly NOT real yet — do not claim otherwise:**

- No client deployments and no production enterprise usage
- No verified inter-agent calling proven through the live UI (the mechanism is proven in isolation; full UI proof is pending)
- The control-plane `audit_events` ledger is append-only and hash-chained; it is now implemented and exportable through `scripts/export_evidence_pack.py`. It is a local evidence mechanism, not a claim of production certification.
- No revenue, no pricing model, no budget of a team that does not exist
- No patent filings, no blockchain integration, no quantum-computing work

---

## Working agreements

This is a **one-person** effort. Everything below is sized for that reality.

1. **Truth over appearance** — a feature is "done" only when it has been run and observed in this session. A plan is a plan until it is executed.
2. **Filesystem over summary** — verify claims with commands, not with descriptions.
3. **Small, honest increments** — one working improvement shipped is worth more than a roadmap of promises.
4. **Anything fabricated is removed** — documents that overstate the project are corrected the same week they are found.

---

## Now (current focus)

1. **Agent inter-communication through the live UI** — the orchestrator and agent mechanisms exist and are proven in isolation; the remaining work is demonstrating a full agent-to-agent flow through the actual cockpit UI.
2. **Automated test coverage** — build and grow the test suite so the alpha's claims are continuously verified by CI.
3. **CI polish** — keep the pre-commit linting pipeline green and extend it where it adds real protection.

## Next (once the above is stable)

1. **Lint and style debt** — Helix Prime carries its own backlog of lint findings (predominantly line-length and style). Cleaning it is real but low-priority, non-functional work.
2. **Documentation consistency** — sweep remaining docs and screens for claims that exceed `MASTER_STORY.md`, and correct them the way this roadmap was corrected.
3. **Demo assets** — rebuild or remove marketing audio/video assets whose scripts contain claims that are not verified (see `CHANGE_LOG.md`).

## Not on the roadmap

- No marketing of features that do not run yet.
- No invented team structure, budgets, or revenue targets.
- No fabricated customer names or "accounts exercised."

---

## Contact

Helix Prime is built and maintained by Hatem Shalaby. Public contact is via the GitHub profile: `github.com/HatemShelby/HatemShelby`.

*Any email addresses ending in `helixprime.io` found in older versions of this repository are fabricated and void.*

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
