"""Smoke tests for the app packaging: compose file and Dockerfile."""
from __future__ import annotations

import pathlib
import re

import pytest
import yaml

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
COMPOSE_PATH = REPO_ROOT / "infra" / "docker" / "docker-compose.app.yml"
DOCKERFILE_PATH = REPO_ROOT / "infra" / "docker" / "Dockerfile.app"
LOCK_PATH = REPO_ROOT / "release" / "requirements.lock.txt"
RUNBOOK_PATH = REPO_ROOT / "docs" / "release" / "app-operator-runbook.md"

_SECRET_ASSIGN = re.compile(r"(?i)\b(password|passwd|secret|api[_-]?token)\b\s*[:=]")


def _non_comment_lines(text: str) -> list[str]:
    return [ln for ln in text.splitlines() if not ln.lstrip().startswith("#")]


def _lock_pins() -> dict[str, str]:
    pins: dict[str, str] = {}
    for line in LOCK_PATH.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith((" ", "#")) or "==" not in line:
            continue
        name, rest = line.split("==", 1)
        pins[name.strip().lower()] = rest.split(";")[0].strip()
    return pins


def _at_least(pin: str, floor: str) -> bool:
    def parts(value: str) -> list[int]:
        return [int(p) for p in re.findall(r"\d+", value)]

    have, need = parts(pin), parts(floor)
    width = max(len(have), len(need))
    have += [0] * (width - len(have))
    need += [0] * (width - len(need))
    return have >= need


@pytest.fixture(scope="module")
def compose_data():
    return yaml.safe_load(COMPOSE_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def dockerfile_text():
    return DOCKERFILE_PATH.read_text(encoding="utf-8")


def test_compose_file_exists():
    assert COMPOSE_PATH.exists()


def test_dockerfile_exists():
    assert DOCKERFILE_PATH.exists()


def test_compose_has_helix_app_service(compose_data):
    services = compose_data.get("services", {})
    assert "helix-app" in services, f"expected helix-app service, got {list(services)}"


def test_compose_only_one_service(compose_data):
    assert len(compose_data.get("services", {})) == 1


def test_compose_healthcheck_hits_app_healthz(compose_data):
    hc = compose_data["services"]["helix-app"]["healthcheck"]
    cmd = hc["test"]
    assert isinstance(cmd, list)
    assert "/app/healthz" in cmd[-1]
    assert "8100" in cmd[-1]


def test_compose_uses_host_networking(compose_data):
    assert compose_data["services"]["helix-app"].get("network_mode") == "host"


def test_compose_has_data_volume(compose_data):
    volumes = compose_data["services"]["helix-app"].get("volumes", [])
    assert any("helix_app_data:/data" in str(v) for v in volumes)


def test_compose_sets_app_env_vars(compose_data):
    env = compose_data["services"]["helix-app"].get("environment", {})
    if isinstance(env, list):
        keys = [v.split("=")[0] for v in env if "=" in v]
    elif isinstance(env, dict):
        keys = list(env.keys())
    else:
        keys = []
    assert "HELIX_APP_DB_PATH" in keys
    assert "HELIX_APP_MEMORY_ROOT" in keys
    assert "HELIX_APP_HOST" in keys


def test_compose_builds_dockerfile_app(compose_data):
    build = compose_data["services"]["helix-app"].get("build", {})
    assert build.get("dockerfile") == "infra/docker/Dockerfile.app"


def test_compose_build_context_is_repo_root(compose_data):
    build = compose_data["services"]["helix-app"].get("build", {})
    assert build.get("context") == "../.."


def test_dockerfile_uses_slim_base(dockerfile_text):
    assert "python:3.12-slim" in dockerfile_text


def test_dockerfile_runs_as_non_root(dockerfile_text):
    assert "USER helix" in dockerfile_text


def test_dockerfile_cmd_is_helix_app(dockerfile_text):
    assert 'CMD ["helix-app"]' in dockerfile_text


def test_dockerfile_exposes_8100(dockerfile_text):
    assert "EXPOSE 8100" in dockerfile_text


def test_dockerfile_healthcheck_hits_8100(dockerfile_text):
    assert "8100" in dockerfile_text
    assert "/app/healthz" in dockerfile_text


def test_dockerfile_declares_data_volume(dockerfile_text):
    assert 'VOLUME ["/data"]' in dockerfile_text


def test_dockerfile_sets_app_db_path(dockerfile_text):
    assert "HELIX_APP_DB_PATH=/data/app.db" in dockerfile_text


def test_dockerfile_sets_memory_root(dockerfile_text):
    assert "HELIX_APP_MEMORY_ROOT=/data/memory_stores" in dockerfile_text


def test_app_default_bind_is_loopback():
    from helix_codex_app.config import AppSettings

    assert AppSettings().host in {"127.0.0.1", "localhost", "::1"}


def test_unsafe_bind_is_rejected():
    from helix_codex_app.config import AppSettings

    with pytest.raises(RuntimeError, match="loopback"):
        AppSettings(host="0.0.0.0").require_safe_defaults()  # noqa: S104


def test_insecure_cookies_require_explicit_ack(monkeypatch):
    from helix_codex_app.config import AppSettings

    monkeypatch.delenv("HELIX_APP_COOKIE_SECURE", raising=False)
    monkeypatch.delenv("HELIX_APP_ALLOW_INSECURE_COOKIES", raising=False)
    AppSettings().require_safe_defaults()
    monkeypatch.setenv("HELIX_APP_COOKIE_SECURE", "false")
    with pytest.raises(RuntimeError, match="ALLOW_INSECURE"):
        AppSettings().require_safe_defaults()
    monkeypatch.setenv("HELIX_APP_ALLOW_INSECURE_COOKIES", "true")
    AppSettings().require_safe_defaults()


def test_constructor_passed_insecure_cookies_still_boots():
    from helix_codex_app.config import AppSettings

    AppSettings(cookie_secure=False).require_safe_defaults()


def test_lock_pins_the_web_stack():
    pins = _lock_pins()
    floors = {
        "fastapi": "0.115",
        "sse-starlette": "2.1",
        "pydantic-settings": "2.5",
        "uvicorn": "0.30",
        "httpx": "0.27",
        "jinja2": "3.1",
        "python-multipart": "0.0.9",
    }
    for name, floor in floors.items():
        assert name in pins, f"{name} missing from the release lock"
        assert _at_least(pins[name], floor), f"{name}=={pins[name]} below floor {floor}"


def test_dockerfile_installs_from_lock(dockerfile_text):
    assert "-r requirements.lock.txt" in dockerfile_text
    assert "-r requirements.txt" not in dockerfile_text.replace("-r requirements.lock.txt", "")


def test_dockerfile_pins_hatchling(dockerfile_text):
    assert "hatchling==" in dockerfile_text


def test_dockerfile_runs_as_non_root_strict(dockerfile_text):
    users = [
        ln.split()[1]
        for ln in _non_comment_lines(dockerfile_text)
        if ln.strip().startswith("USER ")
    ]
    assert users, "no USER directive in the Dockerfile"
    assert users[-1] == "helix"
    assert not any(user in {"root", "0"} for user in users)


def test_compose_declares_no_secrets(compose_data):
    env = compose_data["services"]["helix-app"].get("environment", {})
    keys = list(env.keys()) if isinstance(env, dict) else []
    joined = " ".join(keys).lower()
    assert "password" not in joined
    assert "secret" not in joined
    assert "token" not in joined
    text = "\n".join(_non_comment_lines(COMPOSE_PATH.read_text(encoding="utf-8")))
    assert _SECRET_ASSIGN.search(text) is None


def test_dockerfile_bakes_in_no_secrets(dockerfile_text):
    text = "\n".join(_non_comment_lines(dockerfile_text))
    assert _SECRET_ASSIGN.search(text) is None


def test_compose_healthcheck_is_liveness_only(compose_data):
    cmd = compose_data["services"]["helix-app"]["healthcheck"]["test"][-1]
    assert "/app/healthz" in cmd
    assert "/readyz" not in cmd


def test_compose_allows_graceful_shutdown(compose_data):
    raw = compose_data["services"]["helix-app"].get("stop_grace_period", "")
    match = re.fullmatch(r"(\d+)(s|m)", str(raw).strip())
    assert match is not None, f"stop_grace_period missing or unparsable: {raw!r}"
    total = int(match.group(1)) * (60 if match.group(2) == "m" else 1)
    assert total >= 30


def test_upgrade_procedure_is_documented():
    text = RUNBOOK_PATH.read_text(encoding="utf-8")
    assert "## Upgrade safely (backup first)" in text
    assert "down -v" in text


def test_wheel_build_succeeds_and_exposes_helix_app(tmp_path):
    import subprocess
    import sys
    import zipfile

    out = tmp_path / "dist"
    proc = subprocess.run(
        [sys.executable, "-m", "build", "--wheel", "--no-isolation", "--outdir", str(out)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=110,
    )
    assert proc.returncode == 0, proc.stderr[-2000:]
    wheels = list(out.glob("*.whl"))
    assert wheels, "no wheel produced"
    with zipfile.ZipFile(wheels[0]) as archive:
        entry_points = [name for name in archive.namelist() if name.endswith("entry_points.txt")]
        assert entry_points, "wheel carries no entry points"
        content = archive.read(entry_points[0]).decode("utf-8")
    assert "helix-app" in content
