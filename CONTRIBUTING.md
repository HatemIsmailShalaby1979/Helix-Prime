# Contributing to Helix Prime

## Before you start

Read these documents in order:

1. [00_CONSTITUTION.md](00_CONSTITUTION.md) — the rules we live by
2. [MASTER_STORY.md](MASTER_STORY.md) — what this project actually is right now
3. [GOVERNANCE/](GOVERNANCE/) — decisions, gates, evidence rules
4. [docs/](docs/) — architecture and product explanations

If you haven't read them, don't start coding.

## What we need

- Bug reports with reproduction steps
- Test coverage for gaps you find
- Documentation that corrects stale claims
- Honest assessments of what works and what doesn't

We don't need:
- Features that solve problems nobody has
- Documentation that repeats what the code already says
- Changes without test coverage

## Setup

### Prerequisites

- **Python 3.12** — canonical, for the orchestrator, engines, and API spine
- **Ollama** — for local AI model inference (optional; the system runs without it in deterministic offline mode)
- **Streamlit** — for the cockpit dashboard (a secondary read-only surface)

There is no Go component: the orchestrator is pure Python in `orchestration/`.
Node.js and Docker are **not required** for development; Docker is only needed to
build the deployment profile in `infra/docker/`.

### Local development

```bash
# Clone the repo
git clone https://github.com/HatemIsmailShalaby1979/Helix-Prime.git
cd Helix-Prime

# Create virtual environment
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # Linux/macOS

# Install dependencies
pip install -r requirements.txt -r requirements-dev.txt

# Install pre-commit hooks
pip install pre-commit
pre-commit install
```

## Workflow

### Branches

```bash
git checkout -b feat/your-feature-name    # New feature
git checkout -b fix/bug-description       # Bug fix
git checkout -b docs/update-claim         # Documentation
```

Keep branches focused. One feature, one fix, one documentation update.

### Tests

```bash
pytest tests/ -v --cov
ruff check .
mypy .
pre-commit run --all-files
```

All tests must pass before a PR. If a test fails, fix it — don't suppress it.

### Commit messages

```
feat(engines/wfm): add interval variance detection
fix(agent/recursion): cap depth at 5 to prevent stack overflow
docs: correct agent count from 4 to 9
```

Types: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`, `ci`

## What makes a good PR

1. **Solves a specific problem** — state it in the description
2. **Includes tests** — cover the happy path and the edge case
3. **Updates documentation** — if the behavior changed, the docs should too
4. **Does one thing** — split complex changes into multiple PRs

## Security

- Never commit secrets. Use `.env` (gitignored) for local configuration.
- Memory files (`data/memory/*.json`) and vector stores are in `.gitignore`.
- Dependabot monitors dependencies via `.github/dependabot.yml`.
- See [SECURITY.md](SECURITY.md) for the full policy.

## Getting help

- Architecture questions → `docs/architecture/`
- Agent issues → `SESSION_LOG.md`, `WORKSPACE_AUDIT_REPORT.md`
- Dashboard bugs → `cockpit/tests/`
- Governance questions → `GOVERNANCE/`

## Thank you

Your contributions make this project better. We review every PR carefully.
