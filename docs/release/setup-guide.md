# Helix Prime Codex C8 — Setup Guide (Reproducible Install)

One-document path to a reproducible local setup for the controlled pilot /
production candidate. Backs the `reproducible_install` and `dependency_locking`
release gates.

## Prerequisites

- Python **3.12** (`python3 --version`) — the repo requires `>=3.12,<3.13`.
- `git`, `pip`.

## One-command setup

From the repo root:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt -r requirements-dev.txt
```

The declared dependency set is mirrored in `release/requirements.lock.txt`
(lock reference; byte-level pinning is produced by the package manager).

## Verify

```bash
python3 -m pytest -q          # full suite (all green from a clean tree)
python3 scripts/smoke.py       # engines 6/6, agents 4/4 (registry probes; full 9-agent catalog in organization/role-catalog.yaml)
python3 scripts/health_check.py
python3 scripts/release_gate.py --profile production_candidate
```

## Launch

```bash
helix-api                      # canonical FastAPI spine (loopback 127.0.0.1:8000)
helix-cockpit                  # Streamlit dashboard (secondary)
```

`launch.py --port 8501` remains as a legacy cockpit path.

## Config validation

Configuration (release profiles + manifest schema) is validated before startup
by the `configuration_validation` release gate.

## Ollama (optional)

Ollama is optional and reported with actionable diagnostics when absent.
Engine adapters run in deterministic sample mode without it.

## Clean-room test isolation

Remove the shared local state before a full-suite run to avoid stale-state
flakes:

```bash
rm -f security/audit.db observability/logs.jsonl control_plane/workflow.db
python3 -m pytest -q
```

These files are gitignored and never committed.
