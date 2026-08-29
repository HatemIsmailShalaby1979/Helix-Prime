# Helix Prime — Engineering Specification

## What this is

Helix Prime is a local-first operations platform. It runs six business engines, nine AI agents, and a Streamlit cockpit on your machine. No cloud required.

## The six engines

| Engine | What it does | Key files |
|--------|-------------|-----------|
| WFM | Erlang C staffing, interval forecasting, shrinkage analysis | `engines/wfm/src/app_wfm.py` |
| RTA | Real-time adherence tracking, alert thresholds | `engines/rta/src/app.py` |
| CX | Churn prediction, sentiment analysis, KPI aggregation | `engines/cx/src/kpi_aggregator.py`, `risk_scorer.py` |
| B2B | Client onboarding automation, Notion SOP provisioning | `engines/b2b/src/main.py` |
| Personnel | Hiring pipeline, workforce planning, talent acquisition | `engines/personnel/src/main.py` |
| CRM | Customer support routing, sales pipeline | `engines/crm/src/customer_support.py` |

## The nine agents

| Agent | Role | Calls |
|-------|------|-------|
| SAMI | CEO / Strategist | PHILI, SUBY, WILI |
| SUBY | Operations Executive | PHILI, WILI, SAMI |
| PHILI | Personnel Director | SUBY, SAMI |
| WILI | Training & L&D | PHILI, SUBY |
| ANDY | Compliance & Quality | SUBY, SAMI |
| NONO | Fraud Detection | SUBY, SAMI |
| MAYA | Marketing | SUBY, SAMI |
| LIZA | Sales | SUBY, SAMI |
| TOMY | ICT / Infrastructure | SUBY, SAMI |

Agents route by content. The orchestrator matches the request to the right agent. Agents can call each other when their domain needs input.

## Governance gates

The system uses a gate model from `GOVERNANCE/`. Each gate has a status: PASS, FAIL, or NOT_APPLICABLE. Gates are checked before any external write or deployment action.

## Truth notes

- One repository, not many. The engines, agents, and cockpit live together.
- Local-first means the default path is your machine. Cloud connectors exist as optional adapters.
- Evidence precedes claims. If a feature is documented, there is a test or a verified demonstration.

## Security posture

- No secrets in the repository. `.env` is gitignored.
- Local-first: no mandatory cloud dependency.
- Crash isolation: each engine runs independently.
- No hardcoded configuration.
