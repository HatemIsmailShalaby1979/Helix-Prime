# Contributing to Helix Prime

## Welcome!

Thank you for your interest in contributing to Helix Prime! We appreciate your time and expertise to help make this project better for everyone.

## Getting Started

### 1. Read the Foundations

**MANDATORY:** Before making any changes, read these documents in order:

1. **[ROOT_BOOT.md](ROOT_BOOT.md)** - 🔴 Mandatory first-read for all agents
2. **[SESSION_LOG.md](SESSION_LOG.md)** - Understand recent changes and decisions
3. **[WORKSPACE_AUDIT_REPORT.md](WORKSPACE_AUDIT_REPORT.md)** - Full workspace status
4. **[GOVERNANCE/](GOVERNANCE/)** - Governance and decision records

### 2. Set Up Your Environment

#### Prerequisites

- **Node.js 22+** - Required for development
- **Power Apps CLI** - For deployment
- **Go runtime** - For orchestration daemon
- **Python 3.8+** - For orchestrator
- **Ollama** - For local AI model inference
- **SQLite** - For memory storage
- **Streamlit** - For unified dashboard

#### Local Development

1. Clone the repository
2. Navigate to the project directory
3. Run the development environment:

```bash
python launch.py  # Starts webapp on :5000 and dashboard on :8501
```

### 3. Development Workflow

#### Branch Management

1. **Always create feature branches** from main:
   ```bash
   git checkout -b feat/your-feature-name
   ```

2. **Keep feature branches focused** on single functionality
3. **Prefix your branch names** appropriately:
   - `feat/` - New features
   - `fix/` - Bug fixes
   - `docs/` - Documentation changes
   - `refactor/` - Code refactoring
   - `test/` - Tests
   - `chore/` - Maintenance

#### Code Standards

- **Follow Conventional Commits** (see below)
- **Run pre-commit hooks** before committing
- **Update documentation** when appropriate
- **Log sessions** by appending to SESSION_LOG.md

#### Testing

1. **Run all tests** before opening a pull request:
   ```bash
   pytest tests/ -v --cov
   ```

2. **Run linter and type checker**:
   ```bash
   ruff check .
   mypy .
   ```

3. **Run pre-commit hooks**:
   ```bash
   pre-commit run --all-files
   ```

### 4. Opening Pull Requests

1. **Target the main branch** with your PR
2. **Ensure all CI checks pass** before opening
3. **Add appropriate labels** and assignees
4. **Write a clear PR description**:
   - Summary of changes
   - Motivation/reason for the change
   - Any breaking changes
   - Testing performed

## Code Standards

### Conventional Commits

Your commit messages should follow this format:

```
<type>(<scope>): <description>

<body>

<footer>
```

**Types:**

- `feat` - A new feature
- `fix` - A bug fix
- `docs` - Documentation only changes
- `refactor` - Code refactoring
- `test` - Adding or updating tests
- `chore` - Changes to the build process or auxiliary tools
- `ci` - Changes to CI/CD configuration

**Examples:**

```
feat(helix-prime-ecosystem): add new agent capability
fix(helix-story): resolve dashboard rendering bug
docs: update architecture diagram
refactor(command_center): simplify dispatcher
test: add integration tests for memory layer
chore: update dependencies
ci: add Go test stage
```

### Pre-commit Hooks

To install pre-commit hooks:

```bash
pip install pre-commit
pre-commit install
```

To run all hooks manually:

```bash
pre-commit run --all-files
```

The following checks are performed:

- **ruff** - Code linter and formatter
- **trailing-whitespace** - Removes trailing whitespace
- **end-of-file-fixer** - Ensures proper EOF handling
- **check-yaml** - Validates YAML files
- **check-added-large-files** - Prevents accidentally committing large files
- **check-merge-conflict** - Catches merge conflict markers
- **detect-private-key** - Identifies potential private keys

## Project Structure

The project has two main components:

### Project 1: Helix Prime Ecosystem (`ai-automation-engineering/04-helix-mini/helix-prime-ecosystem/`)

- **Core AI organization** with four agents (SAMI, WILI, PHILI, SUBY)
- **Five business engines** (WFM, RTA, CX, B2B, Personnel)
- **Shared infrastructure** (memory, dashboard, orchestration)

### Project 2: Helix Story Dashboard (`helix-story/`)

- **Streamlit web application** for operator interaction
- **Real-time monitoring** and visualization
- **Deployment scripts** for Azure and cloud

## Security

### Repository Security

- **No secrets in repository** — Use `.env` (gitignored) for local secrets
- **Memory files excluded** — `data/memory/*.json`, `vector_store/` in `.gitignore`
- **Dependencies scanned** — Dependabot enabled via `.github/dependabot.yml`
- **Security policy** — See `SECURITY.md` in each project

### Development Security

- **Always validate and sanitize** user inputs
- **Use parameterized queries** for database operations
- **Never hardcode secrets** in source code
- **Implement proper error handling** without exposing sensitive information
- **Use HTTPS** for all external API calls

## Community Guidelines

### Open to All

We welcome contributions from everyone, regardless of background or experience level. We have a dedicated channel for new contributors and encourage mentorship.

### Communication

- **Be respectful and constructive** in all discussions
- **Ask for help** if you're unsure about anything
- **Share your knowledge** to help others learn
- **Celebrate successes** and learn from failures

## Getting Help

### Documentation

- **Architecture questions** → See `docs/architecture/`
- **Agent issues** → Check `SESSION_LOG.md`, `WORKSPACE_AUDIT_REPORT.md`
- **Dashboard bugs** → `helix-story/tests/`, `TRACING_SETUP.md`
- **Deployment problems** → `helix-story/DEPLOYMENT.md`, `azure.yaml`

### Community

For questions about contributing, please reach out through appropriate channels (GitHub discussions, project communication channels, etc.).

## Thank You!

Your contributions help make Helix Prime better for everyone. We look forward to your involvement!
