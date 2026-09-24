# Helix Prime release-candidate instructions

Helix Prime is a Python 3.12 local-first operations platform. The governed
FastAPI service (`helix-api`) is the canonical release surface. The cockpit,
desktop shell, `helix-app`, and standalone engine services are secondary or
diagnostic surfaces unless their own release evidence says otherwise.

## Canonical commands

| Action | Command |
|---|---|
| Restore locked dependencies | `python -m pip install -r release/requirements.lock.txt` |
| Build package | `python -m build` |
| Run API locally | `helix-api` or `python -m server.cli` |
| Run all non-smoke tests | `python -m pytest tests/ -q -m "not smoke" --cov=server --cov=connectors --cov-fail-under=80` |
| Run release tests | `python -m pytest tests/test_pilot_readiness.py tests/test_c8_release_gate.py -q` |
| Run one test file | `python -m pytest tests/test_pilot_readiness.py -q` |
| Run one test | `python -m pytest tests/test_pilot_readiness.py -q -k policy` |
| Lint | `ruff check server/ connectors/ control_plane/ engines/ capabilities/ security/ pilot/ scripts/ GOVERNANCE/ contracts/ helix_codex_app/ release/ tests/ memory/ metacognition/ organization/ cockpit/` |
| Format check | `ruff format --check .` |
| Typecheck | `mypy server/ connectors/ control_plane/ contracts/ security/` |
| Dependency policy | `python scripts/check_dependencies.py` |
| Migration drift | `python scripts/check_migration_drift.py` |
| Governance drift | `python scripts/check_governance_drift.py` |
| Capability mirror drift | `python scripts/sync_capability_mirrors.py --check` |
| Authority check | `python GOVERNANCE/governance_check.py check` |
| Pilot dry-run | `python scripts/pilot_dry_run.py` |
| Docker config/build | `docker compose -f infra/docker/docker-compose.yml config --quiet` and `docker build --file infra/docker/Dockerfile --tag helix-prime-api:local .` |
| Docker readiness | `docker compose -f infra/docker/docker-compose.yml up -d --build helix-api`; verify `curl --fail http://127.0.0.1:8000/readyz`; then `docker compose -f infra/docker/docker-compose.yml down -v` |

CI is defined in `.github/workflows/ci.yml` and runs on pushes and pull
requests targeting `main`. It runs lint, formatting, typing, tests, security
scans, dependency/governance drift checks, package build, Docker build, and an
API readiness smoke test. Whether CI is an enforced required status check is
**unverified from this checkout** and must be configured manually in GitHub
branch protection.

## Release boundaries

- Keep `controlled_pilot` limited to one tenant, synthetic or explicitly
  consented data, read-only integrations, human approval, and an independent
  peer review.
- Do not weaken or locally satisfy the nine production-only gates.
- Never claim a production release from a pilot or production-candidate
  evidence pack.
- Keep secrets out of source, logs, evidence, and committed configuration.
- Treat `/healthz` as liveness and `/readyz` as traffic readiness.

## Phase and branch discipline

Work one release phase at a time. Keep changes reversible and update the
README, release documentation, and this file whenever commands, topology, or
supported surfaces change. Run the relevant checks before advancing. Prefer a
phase branch and pull request from `main`; merge before starting another phase.
Do not stack unrelated phase branches.

If a check cannot run because the environment lacks Docker, external evidence,
or an optional dependency, record the exact limitation and do not convert it
into a passing release claim.
