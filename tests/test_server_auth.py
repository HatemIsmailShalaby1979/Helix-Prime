"""
Authentication middleware tests (H0.3).

Verifies that all /api routes require a valid bearer token, while /healthz
remains publicly reachable — a design boundary that must not regress.
"""
from __future__ import annotations

import secrets

import pytest

fastapi_testclient = pytest.importorskip("fastapi.testclient")
TestClient = fastapi_testclient.TestClient

# Generated at import, never a literal: the release gate runs a secret scan over the
# whole tree and a hardcoded token here would (correctly) fail security_checks.
TOKEN = secrets.token_urlsafe(24)
WRONG_TOKEN = secrets.token_urlsafe(24)
ROLE = "sami"


@pytest.fixture(autouse=True)
def _token_env(monkeypatch):
    monkeypatch.setenv("HELIX_API_TOKEN", TOKEN)
    monkeypatch.setenv("HELIX_API_TOKEN_ROLE", ROLE)
    monkeypatch.setenv("HELIX_API_TOKEN_TENANT_ID", "tenant-auth")
    monkeypatch.setenv("HELIX_API_TOKEN_CLIENT_ID", "client-auth")


@pytest.fixture()
def client(tmp_path, monkeypatch):
    from server.app import create_app
    from server.config import Settings

    settings = Settings(
        profile="local",
        db_path=str(tmp_path / "workflow.db"),
        audit_db_path=str(tmp_path / "audit.db"),
        log_path=str(tmp_path / "logs.jsonl"),
    )
    with TestClient(create_app(settings)) as test_client:
        yield test_client


def _auth_header():
    return {"Authorization": f"Bearer {TOKEN}"}


def test_healthz_no_token(client):
    """/healthz is the only public endpoint — must return 200 without auth."""
    resp = client.get("/healthz")
    assert resp.status_code == 200


def test_api_no_token(client):
    """Missing Authorization header on /api routes must return 401."""
    resp = client.get("/api/approvals")
    assert resp.status_code == 401


def test_api_wrong_token(client):
    """Invalid token on /api routes must return 401."""
    resp = client.get("/api/approvals", headers={"Authorization": f"Bearer {WRONG_TOKEN}"})
    assert resp.status_code == 401


def test_api_valid_token(client):
    """Valid token on /api routes must return 200 (or a business error)."""
    resp = client.get("/api/approvals", headers=_auth_header())
    # 200 means auth passed; other codes would be business logic errors
    assert resp.status_code == 200


def test_console_no_token(client):
    """Console web UI routes require auth — must return 401 without token."""
    resp = client.get("/")
    assert resp.status_code == 401


def test_console_with_token(client):
    """Console web UI routes are accessible with valid token."""
    resp = client.get("/", headers=_auth_header())
    # Should return 200 with HTML content
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")
