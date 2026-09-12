# Operations Documentation

This directory contains operational runbooks and deployment guides for Helix Prime.

> **Important:** Helix Prime is a single public monorepo at the repo root (`.`). All
> paths below are relative to the repo root. Earlier drafts of this file referenced a
> two-repository layout (`AI OPS Engineering/helix-prime-ecosystem` + `helix-story`)
> that no longer exists — those paths are void.

## Runbooks

| Document | Path | Purpose |
|----------|------|---------|
| Security runbook | `docs/operations/C3-security-runbook.md` | Incident response, secrets scan, audit-chain verification |
| Data retention | `docs/operations/data-retention.md` | Governed-memory expiry policy (flag-based, never deletes) |
| Kubernetes/observer | `infra/`, `observability/` | Monitoring, metrics, alerting |
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
The `engines/rta` Flask service runs loopback-bound on `127.0.0.1:5000` (deny-by-default CORS).

## Presentation Decks

No presentation decks are tracked in this repository as of 2026-08-04. The
`docs/presentations/` decks were removed because they contained fabricated claims
(an invented "proof ledger," "57 auditable entries," and enterprise positioning).
See `CHANGELOG.md` for the audit trail.

## Monitoring & Alerting

- **API**: `helix-api` FastAPI spine (`server/`, loopback-bound). Health: `GET /healthz`.
- **Metrics**: Prometheus exposition at `GET /metrics` (auth-protected); families in
  `observability/metrics.py`; alert rules in `infra/monitoring/alerts.yml`.
- **Logs**: structured `http_request` log lines via the server middleware, PII-redacted.
- **Kill switch**: `POST /api/halt/engage` | `/release` | `GET /api/halt/status` for a
  fail-closed emergency halt.
- **Legacy cockpit**: the Streamlit cockpit (secondary) via `helix-cockpit` or `python launch.py --dash-only`.
