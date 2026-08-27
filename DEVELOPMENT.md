# Helix Prime Project - Development Environment Setup

## Overview

This document provides a comprehensive guide for setting up the development environment for the Helix Prime project. It covers installation, configuration, testing, and continuous integration.

## Installation Instructions

### Prerequisites

Install the following dependencies on your system:

```bash
# Install Node.js 22+
# Visit: https://nodejs.org/en/download/

# Install Power Apps CLI
# Visit: https://learn.microsoft.com/en-us/power-apps/developer/data-platform/power-apps-cli

# Install Go (for orchestration daemon)
# Visit: https://golang.org/doc/install

# Install Python 3.8+
# Visit: https://www.python.org/downloads/

# Install Ollama (for local AI inference)
# Visit: https://ollama.ai/

# Install Streamlit (for dashboard)
# Visit: https://streamlit.io/
```

### Development Setup

```bash
# Navigate to project directory
cd Project\ Helix\ Prime

# Create and activate virtual environment
python -m venv .venv
.venv\Scripts\activate  # Windows
# source .venv/bin/activate  # Linux/macOS

# Install Python dependencies
pip install -r cockpit/requirements.txt

# Install pre-commit hooks for code quality
pip install pre-commit
pre-commit install

# Clone Ollama models
ollama pull llama3.2:latest
ollama pull qwen2.5:7b

# Initialize local database and memory
sqlite3 data/memory/memory.json "VACUUM;"
```

### Alternative Setup (Docker)

For containerized development:

```bash
# Build and run with Docker Compose
docker-compose up -d

# Access the application
# Web UI: http://localhost:5000
# Dashboard: http://localhost:8501
```

## Configuration

### Environment Configuration

Create a `.env` file in the project root (add to `.gitignore`):

```env
# AI Model Configuration
HELIX_MODEL_BACKEND=ollama
HELIX_MODEL_NAME=llama3.2:latest

# Database Configuration
HELIX_DATABASE_URL=sqlite:///data/memory/memory.db

# Orchestration Configuration
HELIX_ORCHESTRATION_PORT=8080
HELIX_AGENT_TIMEOUT=30

# Security Configuration
HELIX_ENCRYPTION_KEY=your-32-character-encryption-key-here
HELIX_SESSION_SECRET=your-random-session-secret

# Monitoring Configuration
HELIX_LOG_LEVEL=INFO
HELIX_METRICS_PORT=9090

# Dashboard Configuration
HELIX_DASHBOARD_PORT=8501
HELIX_DASHBOARD_HOST=localhost
```

### Configuration Management

The project uses a layered configuration approach:

1. **Environment Variables**: Runtime configuration (highest priority)
2. **Configuration Files**: Project settings (medium priority)
3. **Default Values**: Built-in defaults (lowest priority)

### Configuration Files

Configuration is stored in multiple files for different purposes:

- **`cockpit/.env.example`**: Template for development environment
- **`.github/dependabot.yml`**: Dependency update configuration
- **`pytest.ini`**: Test configuration
- **`.flake8`**: Linting configuration
- **`.pre-commit-config.yaml`**: Pre-commit hooks configuration

## Testing

### Running Tests

```bash
# Navigate to project directory
cd Project\ Helix\ Prime

# Activate virtual environment
.venv\Scripts\activate

# Run all tests
pytest tests/ -v --cov

# Run specific test modules
pytest cockpit/functional_test.py -v
pytest app/command_center/agents/test_agent_examples.py -v

# Run integration tests
pytest engines/wfm/tests/ -v
pytest engines/rta/tests/ -v

# Run tests with coverage report
pytest --cov=. --cov-report=html --cov-report=xml --cov-report=term
```

### Test Structure

The project uses pytest with comprehensive test coverage:

#### Test Categories

1. **Unit Tests**: Individual component testing
   - `tests/unit/`
   - Mock external dependencies
   - Fast execution

2. **Integration Tests**: Component interaction testing
   - `tests/integration/`
   - Real dependencies
   - Slow execution

3. **Functional Tests**: End-to-end scenario testing
   - `tests/functional/`
   - Complete user workflows
   - Most comprehensive

4. **Performance Tests**: Load and stress testing
   - `tests/performance/`
   - Performance benchmarks
   - Scalability testing

#### Test Files

Example test file structure:

```python
# tests/unit/test_agent_base.py
import pytest
from app.command_center.agents.base_agent import BaseAgent

class TestBaseAgent:
    def test_agent_initialization(self):
        """Test agent initialization with default settings"""
        agent = BaseAgent("test-agent", {})
        assert agent.name == "test-agent"
        assert agent.settings == {}

    def test_agent_capability_check(self):
        """Test capability checking"""
        agent = BaseAgent("test-agent", {})
        assert agent.has_capability("general_reasoning")
        assert not agent.has_capability("nonexistent_capability")
```

### Test Coverage Requirements

- **Unit Tests**: 90%+ coverage
- **Integration Tests**: 80%+ coverage
- **Functional Tests**: 70%+ coverage
- **Performance Tests**: 50%+ coverage (project-specific)

## Code Quality

### Pre-commit Hooks

The project uses pre-commit hooks to enforce code quality:

```bash
# Install pre-commit hooks (one-time setup)
pre-commit install

# Run all hooks on all files
pre-commit run --all-files

# Run specific hooks
pre-commit run ruff --all-files
pre-commit run trailing-whitespace --all-files
pre-commit run end-of-file-fixer --all-files
```

### Code Linting

The project uses multiple code quality tools:

#### Ruff (Linter and Formatter)

```bash
# Check code style
ruff check .

# Format code automatically
ruff format .

# Fix simple issues automatically
ruff check . --fix
```

#### mypy (Type Checking)

```bash
# Install mypy
pip install mypy

# Run type checking
mypy .

# Run type checking with strict mode
mypy --strict .
```

#### Flake8 (Legacy Code Quality)

```bash
# Install flake8
pip install flake8

# Run flake8
flake8 .
```

### Code Quality Standards

#### Naming Conventions

- **Classes**: `PascalCase` (e.g., `BaseAgent`)
- **Functions**: `snake_case` (e.g., `initialize_agent`)
- **Variables**: `snake_case` (e.g., `agent_config`)
- **Constants**: `UPPER_SNAKE_CASE` (e.g., `MAX_AGENT_COUNT`)

#### Documentation Standards

- **Docstrings**: Use Google style format
- **Comments**: Brief, informative, and inline where necessary
- **README**: Comprehensive overview with examples
- **API Documentation**: Auto-generated with Sphinx (planned)

#### Code Structure

- **Single Responsibility**: Each class/function should have one purpose
- **Open/Closed Principle**: Open for extension, closed for modification
- **Dependency Injection**: Avoid hard-coded dependencies
- **Error Handling**: Proper exception handling and logging

## GitHub Integration

### Repository Structure

The project uses a multi-repository structure:

```
Project Helix Prime/
├── .github/                    # GitHub configuration
│   ├── workflows/             # CI/CD workflows
│   └── dependabot.yml         # Dependency updates
│
├── cockpit/                    # Operations Control Room
│   ├── cockpit.py              # Main dashboard application
│   ├── requirements.txt        # Python dependencies
│   ├── .env.example           # Environment configuration
│   └── tests/                 # Application tests
│
├── app/                        # Command Center
│   ├── command_center/         # Agent orchestration
│   ├── orchestration/          # Go daemon
│   └── rag/                    # Vector memory
│
├── engines/                    # Business Engines
│   ├── wfm/                    # WFM Forecasting
│   ├── rta/                    # RTA Command Center
│   ├── cx/                     # CX Churn Sentinel
│   ├── b2b/                    # B2B Onboarding
│   └── personnel/              # Personnel Engine
│
├── data/                       # Metacognitive Memory
│   └── memory/                 # TMK Loop storage
│
├── helix-story/                # Web Dashboard
│   └── helix-story/            # Streamlit application
│
├── GOVERNANCE/                 # Constitutional governance
│   ├── CHANGE_LOG.md           # Append-only changelog
│   ├── DECISION_LOG.md         # Critical decisions
│   └── audit-log/              # Security audits
│
├── docs/                       # Technical documentation
│   └── architecture/           # Architecture documentation
│
└── scripts/                    # Deployment scripts
    ├── deploy.sh               # Deployment automation
    └── cleanup.py              # Cleanup automation
```

### GitHub Workflows

#### CI/CD Pipeline (`.github/workflows/ci.yml`)

The CI/CD pipeline includes:

1. **Test Matrix**: Multiple Python versions
2. **Code Quality Checks**: Linting, formatting, type checking
3. **Security Scans**: Vulnerability scanning
4. **Coverage Reporting**: Test coverage analysis
5. **Artifact Upload**: Test results and coverage reports
6. **Deployment Gates**: Approval gates for production

#### Dependabot Configuration (`.github/dependabot.yml`)

Automatic dependency updates:

- **Python dependencies**: Weekly updates
- **GitHub Actions**: Weekly updates
- **Docker images**: Weekly updates
- **OpenPRs limit**: Configurable for each ecosystem

### GitHub Actions

#### Code Quality Actions

- **`run-linter.yml`**: Ruff, mypy, flake8
- **`run-tests.yml`**: Unit, integration, functional tests
- **`security-scan.yml`**: Bandit, safety, dependency scanning

#### Deployment Actions

- **`deploy-prod.yml`**: Production deployment
- **`deploy-staging.yml`**: Staging deployment
- **`release.yml`**: Release automation

## Advanced Development

### Local Development

#### IDE Configuration

Editor configuration files:

- **`.vscode/settings.json`**: VS Code settings
- **`.vscode/tasks.json`**: VS Code tasks
- **`.vscode/launch.json`**: VS Code debugging

#### Debugging

Start debugging with:

```bash
# Start debugging the main dashboard
cd cockpit
cockpit.py

# Debug orchestration daemon
orchestration/main.go

# Debug agent operations
python debug_agents.py
```

### Performance Testing

#### Load Testing

```bash
# Install load testing tools
pip install k6 locust pytest-performance

# Run performance tests
k6 run load_tests/agent_performance.k6.js
locust -f locustfile.py
pytest tests/performance/ -v
```

#### Memory Monitoring

```bash
# Monitor memory usage
python scripts/monitor_memory.py

# Profile memory usage
python -m memory_profiler tests/performance/test_memory_usage.py
```

## Troubleshooting

### Common Issues

#### "UnicodeEncodeError: 'charmap' codec can't encode"

**Issue**: Windows console encoding issues with special characters.

**Solution**: Ensure output uses ASCII-only strings:

```python
# Instead of this:
print("✓ Success with emoji")

# Use this:
print("✓ Success")
```

#### "ModuleNotFoundError: No module named 'ollama'"

**Issue**: Ollama Python client not installed.

**Solution**:

```bash
pip install ollama
```

#### "ImportError: No module named 'streamlit'"

**Issue**: Streamlit not installed.

**Solution**:

```bash
pip install streamlit
```

#### "Connection refused: Unable to connect to Ollama server"

**Issue**: Ollama service not running.

**Solution**:

```bash
# Start Ollama service
ollama serve

# Or install and start via package manager
# sudo systemctl start ollama
```

### Getting Help

#### Project Documentation

- **Architecture**: `docs/architecture/`
- **API Reference**: `docs/api/`
- **Deployment**: `helix-story/DEPLOYMENT.md`
- **Configuration**: `docs/configuration/`

#### GitHub Resources

- **Issues**: File issues in the repository
- **Discussions**: GitHub Discussions
- **Pull Requests**: Submit feature requests or fixes

#### Community Support

- **GitHub Issues**: File issues in the repository
- **GitHub Discussions**: Project-specific discussion channel
- **Stack Overflow**: Tag with `#helix-prime`
- **Email**: The support@helixprime.io address listed in earlier drafts was fabricated and is void. Contact the maintainer via `github.com/HatemShelby/HatemShelby`.

## Contributing Guidelines

### Development Process

1. **Plan**: Review existing issues and feature requests
2. **Design**: Document your changes in `docs/`
3. **Code**: Implement changes following code quality standards
4. **Test**: Write comprehensive tests
5. **Review**: Get peer review
6. **Document**: Update documentation
7. **Release**: Create and publish release

### Code Review Standards

- **Code**: Clean, readable, and well-documented
- **Tests**: Comprehensive with >90% coverage
- **Design**: Follows SOLID principles
- **Performance**: Meets performance requirements
- **Security**: Passes security review

### Commit Standards

- **Format**: `type(scope): description`
- **Types**: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`, `ci`
- **Body**: Detailed description of changes
- **Footer**: References issues and breaking changes

## Setup Validation

Run this validation script to ensure your development environment is correctly set up:

```python
#!/usr/bin/env python3
"""Development environment validation script"""

import os
import sys
import subprocess
import platform

def check_python_version():
    """Check Python version"""
    version = sys.version_info
    if version.major < 3 or (version.major == 3 and version.minor < 8):
        return False, f"Python 3.8+ required, found {version.major}.{version.minor}"
    return True, f"Python {version.major}.{version.minor} OK"

def check_dependencies():
    """Check required Python dependencies"""
    required_packages = [
        'streamlit',
        'pandas',
        'numpy',
        'flask',
        'scipy',
        'scikit-learn',
        'ollama',
        'pytest'
    ]

    missing = []
    for package in required_packages:
        try:
            __import__(package.replace('-', '_'))
        except ImportError:
            missing.append(package)

    if missing:
        return False, f"Missing dependencies: {', '.join(missing)}"
    return True, "All required Python dependencies OK"

def check_directories():
    """Check project directory structure"""
    required_dirs = [
        'cockpit',
        'app/command_center',
        'engines/wfm',
        'engines/rta',
        'engines/cx',
        'engines/b2b',
        'engines/personnel',
        'data/memory',
        'helix-story'
    ]

    missing = []
    for directory in required_dirs:
        if not os.path.exists(directory):
            missing.append(directory)

    if missing:
        return False, f"Missing directories: {', '.join(missing)}"
    return True, "All required directories OK"

def check_git_config():
    """Check git configuration"""
    try:
        # Check git version
        result = subprocess.run(['git', '--version'], capture_output=True, text=True)
        if result.returncode != 0:
            return False, "Git not available"

        # Check user email
        result = subprocess.run(['git', 'config', 'user.email'], capture_output=True, text=True)
        if not result.stdout or '@' not in result.stdout:
            return False, "Git user.email not configured"

        # Check user name
        result = subprocess.run(['git', 'config', 'user.name'], capture_output=True, text=True)
        if not result.stdout or len(result.stdout.strip()) == 0:
            return False, "Git user.name not configured"

        return True, "Git configuration OK"
    except Exception as e:
        return False, f"Git configuration check failed: {e}"

def main():
    """Main validation function"""
    print("=== Helix Prime Development Environment Validation ===\n")

    checks = [
        ("Python Version", check_python_version),
        ("Python Dependencies", check_dependencies),
        ("Project Directories", check_directories),
        ("Git Configuration", check_git_config)
    ]

    all_passed = True
    for name, check_func in checks:
        passed, message = check_func()
        status = "✓" if passed else "✗"
        print(f"{status} {name}: {message}")
        if not passed:
            all_passed = False

    print("\n=== Summary ===")
    if all_passed:
        print("✓ All checks passed! Your development environment is ready.")
        return 0
    else:
        print("✗ Some checks failed. Please review the issues above.")
        print("\nTo fix these issues:")
        print("1. Follow the installation instructions in this guide")
        print("2. Run the validation script again to confirm")
        return 1

if __name__ == '__main__':
    sys.exit(main())
```

### Using the Validation Script

```bash
# Make the script executable
chmod +x validate_setup.py

# Run the validation
python validate_setup.py
```

## Conclusion

This comprehensive development environment guide provides everything needed to set up, configure, and maintain the Helix Prime project. By following these instructions, developers can quickly get up to speed with the project and contribute effectively.

For any questions or issues, refer to the troubleshooting section or seek help from the project team.
