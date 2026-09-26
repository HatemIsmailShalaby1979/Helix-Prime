from __future__ import annotations

import pytest

TestClient = pytest.importorskip("fastapi.testclient").TestClient

from helix_codex_app import db
from helix_codex_app.app import create_app
from helix_codex_app.config import AppSettings
from helix_codex_app.modules.identity import router
from helix_codex_app.security.accounts import DEMO_ROLE_ID


@pytest.fixture()
def fresh_client(tmp_path):
    settings = AppSettings(
        db_path=str(tmp_path / "fresh-supabase.db"),
        cookie_secure=False,
        supabase_url="https://project.supabase.co",
        supabase_anon_key="publishable-test-key",
        supabase_redirect_uri="https://app.example.test/app/auth/supabase/callback",
    )
    with TestClient(create_app(settings), follow_redirects=False) as client:
        yield client, settings


def test_supabase_callback_bridges_a_fresh_identity_to_demo_session(monkeypatch, fresh_client):
    client, settings = fresh_client

    started = client.get("/app/auth/supabase/login")
    assert started.status_code == 303
    assert "provider=github" in started.headers["location"]
    state = client.cookies["supabase_oauth_state"]
    client.cookies.set("supabase_oauth_verifier", "fresh-verifier")

    async def fake_exchange(*args):
        return {"id": "github-user-fresh", "email": "visitor@example.com"}

    monkeypatch.setattr(router, "exchange_code", fake_exchange)
    callback = client.get(
        "/app/auth/supabase/callback?code=one-use-code&state=" + state,
    )
    assert callback.status_code == 303
    assert callback.headers["location"] == "/app/ops"
    assert client.get("/app/ops").status_code == 200

    conn = db.connect(db_path=settings.db_path)
    try:
        row = conn.execute(
            "SELECT role_id, email FROM accounts WHERE username = 'demo'"
        ).fetchone()
    finally:
        db.close(conn)
    assert tuple(row) == (DEMO_ROLE_ID, "visitor@example.com")