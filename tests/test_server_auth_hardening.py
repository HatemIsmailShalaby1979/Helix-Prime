"""Fail-closed hardening for server/auth.py::current_identity (Prompt F2).

Covers three defects:
  (a) an unset/empty/blank HELIX_API_TOKEN must refuse with a clear error and can
      never authenticate;
  (b) tokens are compared as UTF-8 bytes, so a non-ASCII bearer token yields 401
      rather than a TypeError that escapes as a 500;
  (c) HELIX_API_TOKEN_ROLE no longer defaults to "sami" — unset or blank fails
      closed with 500 instead of silently authenticating as a privileged seat.
"""
from __future__ import annotations

import secrets

import pytest

fastapi_testclient = pytest.importorskip("fastapi.testclient")
TestClient = fastapi_testclient.TestClient

TOKEN = secrets.token_urlsafe(24)


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("HELIX_API_TOKEN", TOKEN)
    monkeypatch.setenv("HELIX_API_TOKEN_ROLE", "sami")
    monkeypatch.setenv("HELIX_API_TOKEN_TENANT_ID", "tenant-auth")
    monkeypatch.setenv("HELIX_API_TOKEN_CLIENT_ID", "client-auth")
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


def _auth() -> dict[str, str]:
    return {"Authorization": f"Bearer {TOKEN}"}


def test_token_unset_refuses_with_clear_error(client, monkeypatch):
    monkeypatch.delenv("HELIX_API_TOKEN", raising=False)
    resp = client.get("/api/approvals", headers=_auth())
    assert resp.status_code == 500
    assert "HELIX_API_TOKEN" in resp.json()["detail"]


def test_token_empty_refuses_with_clear_error(client, monkeypatch):
    monkeypatch.setenv("HELIX_API_TOKEN", "")
    resp = client.get("/api/approvals", headers=_auth())
    assert resp.status_code == 500
    assert "HELIX_API_TOKEN" in resp.json()["detail"]


def test_blank_token_refuses_with_clear_error(client, monkeypatch):
    monkeypatch.setenv("HELIX_API_TOKEN", "   ")
    resp = client.get("/api/approvals", headers=_auth())
    assert resp.status_code == 500
    assert "HELIX_API_TOKEN" in resp.json()["detail"]


def test_non_ascii_token_is_401_not_500(client):
    """Raw UTF-8 bytes ride the wire; Starlette decodes latin-1, so the server sees a
    non-ASCII str -- the input that used to trip compare_digest's str guard."""
    headers = [(b"Authorization", "Bearer café-🔑".encode("utf-8"))]
    resp = client.get("/api/approvals", headers=headers)
    assert resp.status_code == 401


def test_missing_role_fails_closed(client, monkeypatch):
    monkeypatch.delenv("HELIX_API_TOKEN_ROLE", raising=False)
    resp = client.get("/api/approvals", headers=_auth())
    assert resp.status_code == 500
    assert "HELIX_API_TOKEN_ROLE" in resp.json()["detail"]


def test_blank_role_fails_closed(client, monkeypatch):
    monkeypatch.setenv("HELIX_API_TOKEN_ROLE", "   ")
    resp = client.get("/api/approvals", headers=_auth())
    assert resp.status_code == 500
    assert "HELIX_API_TOKEN_ROLE" in resp.json()["detail"]
