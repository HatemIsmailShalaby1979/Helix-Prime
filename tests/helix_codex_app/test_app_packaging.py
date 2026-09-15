"""Smoke tests for the app packaging: compose file and Dockerfile."""
from __future__ import annotations

import pathlib

import pytest
import yaml

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
COMPOSE_PATH = REPO_ROOT / "infra" / "docker" / "docker-compose.app.yml"
DOCKERFILE_PATH = REPO_ROOT / "infra" / "docker" / "Dockerfile.app"


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
