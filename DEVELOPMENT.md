# Development Guide

## Quick start

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt -r requirements-dev.txt
pytest tests/ -q -m "not smoke"
helix-api
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000) — that is the governed API spine,
the one deployable artifact. The Streamlit cockpit is a secondary read-only
diagnostic surface on port 8501 (`helix-cockpit`, equivalent to `python launch.py`).

## What you need

- **Python 3.12** — canonical. The engines, orchestrator, and API all run on this
- **Ollama** — optional. Without it, the system runs in deterministic offline mode
- **SQLite** — comes with Python, no separate install needed

Node.js and Docker are **not required** for development. Docker is only needed to
build the deployment profile in `infra/docker/`. There is no Go component: the
orchestrator is pure Python in `orchestration/`.

## Project structure

```
Helix-Prime/
├── app/command_center/     # Agent implementations and registry
├── helix_codex_app/        # The daily-use product layer (identity, chat, docs,
│                           #   tasks, calendar, attendance, low-code loader)
├── cockpit/                # Streamlit dashboard (secondary, read-only)
├── engines/                # Six business engines (wfm, rta, cx, b2b, personnel, crm)
├── capabilities/           # Vertical capability packs (restaurant = reference pattern,
│                           #   sports_academy = first real vertical)
├── control_plane/          # Governed core: workflow, governance, audit, approvals
├── organization/           # role-catalog.yaml — the source of truth for the 9 roles
├── release/                # C8 release gate, profiles, manifest, security gate
├── server/                 # The FastAPI spine (`helix-api`)
├── tests/                  # The full suite, across contracts, security, engines, gates
├── GOVERNANCE/             # Decisions, gates, evidence rules
├── docs/                   # Architecture and product documentation
└── launch.py               # Legacy Streamlit launcher (superseded by helix-cockpit)
```

## Running tests

```bash
pytest tests/ -q -m "not smoke"     # Full suite, canonical invocation
pytest tests/test_c1_contracts.py   # Single test file
pytest tests/ --cov                 # With coverage
```

Run the suite from the repository root. `-m "not smoke"` excludes the smoke-marked
tests that require a live service.

> **Windows note.** Under a sandbox that routes deletions through a guarded trash
> step, the full suite can fail on temp-directory teardown rather than on real
> assertions. If you see failures that look like cleanup errors, raise the
> bulk-delete threshold for the run:
> `CODEBUDDY_SAFE_DELETE_BULK_THRESHOLD=100000 pytest tests/ -q -m "not smoke"`.
> The cause is that pytest always prefixes temp paths with `\\?\` on Windows,
> which defeats the guard's own exemption check. See `AGENTS.md` §18.4.

Target coverage: 90%+ on contracts and control plane, 80%+ on engines.

## Code standards

- **Linting:** `ruff check .` · **Formatting:** `ruff format --check .`
- **Type checking:** `mypy .`
- **Pre-commit hooks:** install with `pip install pre-commit && pre-commit install`
- **Commits:** conventional format — `feat(engine/wfm):`, `fix(agent):`, `docs:`, `test:`

Note: `ruff` is pinned to `0.1.15` in `requirements-dev.txt`; newer versions report
a different finding set on this codebase.

## Adding a new engine

1. Create `engines/{name}/` with a `README.md` describing the engine's purpose
2. Add tests in `tests/test_{name}.py`
3. Register it in `engines/registry.py` so the control plane can reach it
4. Update `requirements.txt` if the engine has new dependencies

## Adding a new capability pack

Copy the shape of `capabilities/restaurant/` — it is the reference pattern, and
copying it is a hard rule rather than a preference. Do not invent a new structure.
Roles stay pack-local (`capabilities/<pack>/declarations/`); engines are reused
through existing capability ids. Never edit `organization/role-catalog.yaml`,
`control_plane/governance.py`, or `organization/capability-registry.yaml` for a pack.

## Debugging agent calls

Agents log to `cockpit/memory/cognitive_log.py`. Each interaction records:
- Timestamp
- Agent name
- User input
- Agent output
- Reasoning trace (if visible)
- Inter-agent calls made

Check the log when an agent returns unexpected output.

## Common issues

**"Module not found" after `pip install`:**
Run `pip install -r requirements.txt -r requirements-dev.txt` from the repo root,
not from a subdirectory.

**Ollama connection refused:**
Start Ollama and pull a model first:
```bash
ollama pull qwen3:8b
```

**Tests failing with "shared database" errors:**
Run the failing file in isolation, or run the suite in parallel groups (requires
`pytest-xdist`, which is not currently in `requirements-dev.txt`):
```bash
pip install pytest-xdist
pytest tests/ --dist=loadgroup
```

**Gate probes rewrite release artifacts:**
`release/gate.py` writes `release/release-manifest.json` by default. When probing a
gate, pass `write_evidence=False` unless you intend to rewrite the manifest.

## Where to find things

- Architecture decisions → `docs/architecture/`
- Governance rules → `GOVERNANCE/`
- Agent implementations → `app/command_center/agents/`
- Engine code → `engines/{name}/src/`
- Dashboard code → `cockpit/cockpit.py`
- Release gate → `release/gate.py`; profiles → `release/release-profiles.yaml`

## What not to do

- Don't commit secrets. Use `.env` (gitignored).
- Don't add cloud dependencies. This project is local-first.
- Don't claim production readiness. The status is `CONTROLLED_PILOT_READY`.
- Don't add features without tests. Every new capability needs test coverage.
- Don't fabricate a governance record. A change that manufactures an approval,
  signature, or `production_approved` sign-off is a defect and must be rejected in
  review — see `docs/release/production-blockers.md`.

