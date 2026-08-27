# Operations Documentation

This directory contains operational runbooks and deployment guides for Helix Prime.

> **Important:** Helix Prime is a single public monorepo at the repo root (`.`). All
> paths below are relative to the repo root. Earlier drafts of this file referenced a
> two-repository layout (`AI OPS Engineering/helix-prime-ecosystem` + `helix-story`)
> that no longer exists — those paths are void.

## Runbooks

| Document | Path | Purpose |
|----------|------|---------|
| Agent runbook | `app/command_center/` | Local operations for core agent system (SAMI/WILI/PHILI/SUBY) |
| Deployment scaffolding | `marketing/` | Marketing site deployment (Render, Azure, Docker) |

## Deployment Configs

| File | Location | Purpose |
|------|----------|---------|
| Render blueprint | `marketing/render.yaml` | Marketing site deploy |
| Dockerfile | `marketing/Dockerfile` | Container build for marketing site |
| Azure config | `marketing/azure.yaml` | Azure deployment scaffolding |
| Infrastructure | `marketing/infra/main.bicep` | Azure Static Web Apps template |

None of these files is evidence of a hosted production service. Helix Prime is a
public alpha; there are no client deployments or production enterprise usage.

## Engine Operations

Each engine in `engines/{b2b,cx,crm,personnel,rta,wfm}/` is independently runnable and
has its own README. See `docs/ENGINEERING_SPECIFICATION.md` for per-engine notes.

## Presentation Decks

No presentation decks are tracked in this repository as of 2026-08-04. The
`docs/presentations/` decks were removed because they contained fabricated claims
(an invented "proof ledger," "57 auditable entries," and enterprise positioning).
See `GOVERNANCE/CHANGE_LOG.md` for the audit trail.

## Monitoring & Alerting

- **Dashboard**: Streamlit Operations Cockpit via `python launch.py --dash-only` (port 8501)
- **Logs**: Cognitive log in `cockpit/memory/`
- **Memory audit**: JSON memory and ChromaDB store under `memory/` and `06_memory/`
