# Development Guide

## Quick start

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r cockpit/requirements.txt
pip install -r dev-requirements.txt
pytest tests/ -v
python launch.py
```

Open [http://localhost:8501](http://localhost:8501).

## What you need

- **Python 3.11+** — the engines and orchestrator run on this
- **Go** — only if you're modifying the orchestration daemon
- **Ollama** — optional. Without it, the system runs in deterministic offline mode
- **SQLite** — comes with Python, no separate install needed

Node.js, Power Apps CLI, and Docker are **not required** for Helix Prime development.

## Project structure

```
Helix-Prime/
├── app/command_center/     # Agent implementations and registry
├── cockpit/                # Streamlit dashboard
├── engines/                # Business engines (wfm, rta, cx, b2b, personnel, crm)
├── control_plane/          # Orchestration and routing
├── tests/                  # 445 tests across contracts, security, engines
├── GOVERNANCE/             # Decisions, gates, evidence rules
├── docs/                   # Architecture and product documentation
└── launch.py               # Starts the cockpit
```

## Running tests

```bash
pytest tests/ -v                    # Full suite
pytest tests/test_c1_contracts.py   # Single test file
pytest tests/ --cov                 # With coverage
```

Target coverage: 90%+ on contracts and control plane, 80%+ on engines.

## Code standards

- **Linting:** `ruff check .`
- **Type checking:** `mypy .`
- **Pre-commit hooks:** install with `pip install pre-commit && pre-commit install`
- **Commits:** conventional format — `feat(engine/wfm):`, `fix(agent):`, `docs:`, `test:`

## Adding a new engine

1. Create `engines/{name}/` with a `README.md` describing the engine's purpose
2. Add tests in `tests/test_{name}.py`
3. Register in the orchestrator if it needs external routing
4. Update `cockpit/requirements.txt` if the engine has new dependencies

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
Run `pip install -r cockpit/requirements.txt` from the repo root, not from a subdirectory.

**Ollama connection refused:**
Start Ollama and pull a model first:
```bash
ollama pull qwen3:8b
```

**Tests failing with "shared database" errors:**
Run tests in isolation:
```bash
pytest tests/ --dist=loadgroup
```

## Where to find things

- Architecture decisions → `docs/architecture/`
- Governance rules → `GOVERNANCE/`
- Agent implementations → `app/command_center/agents/`
- Engine code → `engines/{name}/src/`
- Dashboard code → `cockpit/cockpit.py`

## What not to do

- Don't commit secrets. Use `.env` (gitignored).
- Don't add cloud dependencies. This project is local-first.
- Don't claim production readiness. The status is `CONTROLLED_PILOT_READY`.
- Don't add features without tests. Every new capability needs test coverage.
