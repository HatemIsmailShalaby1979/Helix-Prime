# Helix Prime Codex C8 — Operator Runbook

Status: **Production Candidate / Controlled Pilot** (NOT production)

This runbook documents the local-first operational procedures an operator follows
to stand up, validate, and run Helix Prime as a controlled pilot or production
candidate. It is part of the C8 `operator_readiness` release gate.

## 1. Scope and boundary

- Local-only deployable bundle; SQLite persistence; in-process sibling transport.
- No cloud deployment, no external IdP, no cloud observability, no network
  sibling transport.
- Pilot data MUST be limited to **synthetic or explicitly consented** data.

## 2. Prerequisites

- Python 3.10+ on PATH (`python3 --version`).
- A clean checkout of the `main` branch (see `docs/release/setup-guide.md`).

## 3. Reproducible setup (one-time)

```bash
python3 -m venv .venv
.venv/bin/pip install -r release/requirements.lock.txt
python3 -m pytest -q          # full suite (expect all green from clean tree)
python3 scripts/smoke.py       # engines 6/6, agents 4/4
```

See `docs/release/setup-guide.md` for the full one-doc install path.

## 4. Health / readiness check

```bash
python3 scripts/health_check.py
```

Required components (control-plane store, event replay, capability registry,
role catalog, filesystem) must be ready. Ollama is **optional** and reported
separately with actionable diagnostics when absent.

## 5. Release gate

```bash
python3 scripts/release_gate.py --profile production_candidate
python3 scripts/release_gate.py --profile controlled_pilot
```

Expected result: `PRODUCTION_CANDIDATE` or `CONTROLLED_PILOT_READY`.
An unqualified `PRODUCTION` label is **never** emitted by this gate.

## 6. Starting the cockpit

```bash
python3 launch.py --port 8501
```

## 7. Operational limits

- DBs: `control_plane/workflow.db`, `security/audit.db` (local SQLite).
- Logs: `observability/logs.jsonl` (gitignored).
- Backup/restore/rollback: see `docs/release/backup-restore-guide.md`.

## 8. No autonomous irreversible actions

Operators must approve any irreversible, financial, personnel, compliance,
ICT, or external-communication action before it proceeds. The system is deny-by-
default and requires explicit approval for such actions.
