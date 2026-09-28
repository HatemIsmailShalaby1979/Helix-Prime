from __future__ import annotations

from urllib.parse import parse_qs, urlsplit

import pytest

TestClient = pytest.importorskip("fastapi.testclient").TestClient

from helix_codex_app import db
from helix_codex_app.app import create_app
from helix_codex_app.config import AppSettings
from helix_codex_app.modules.identity import router
from helix_codex_app.modules.identity.supabase import SupabaseAuthError
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
    location = started.headers["location"]
    assert "provider=github" in location
    state = client.cookies["supabase_oauth_state"]
    client.cookies.set("supabase_oauth_verifier", "fresh-verifier")

    authorize = urlsplit(location)
    redirect_to = parse_qs(authorize.query)["redirect_to"][0]
    assert redirect_to == f"{settings.supabase_redirect_uri}?state={state}"

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
        row = conn.execute("SELECT role_id, email FROM accounts WHERE username = 'demo'").fetchone()
    finally:
        db.close(conn)
    assert tuple(row) == (DEMO_ROLE_ID, "visitor@example.com")


def test_the_login_page_offers_the_github_entry(fresh_client):
    client, _settings = fresh_client

    page = client.get("/app/auth/login")

    assert page.status_code == 200
    assert 'href="/app/auth/supabase/login"' in page.text
    assert "Sign in with GitHub" in page.text


def test_the_login_page_hides_the_github_entry_when_supabase_is_unconfigured(tmp_path):
    settings = AppSettings(
        db_path=str(tmp_path / "no-supabase.db"),
        cookie_secure=False,
        supabase_url=None,
        supabase_anon_key=None,
        supabase_redirect_uri=None,
    )
    with TestClient(create_app(settings), follow_redirects=False) as client:
        page = client.get("/app/auth/login")

    assert page.status_code == 200
    assert "Sign in with GitHub" not in page.text
    assert 'href="/app/auth/supabase/login"' not in page.text


def test_supabase_auth_error_carries_a_status_and_a_detail():
    error = SupabaseAuthError(
        "Supabase authorization code exchange failed",
        status=401,
        detail="Invalid API key",
    )
    assert error.status == 401
    assert error.detail == "Invalid API key"
    assert str(error) == "Supabase authorization code exchange failed"

    bare = SupabaseAuthError("Supabase did not return an access token")
    assert bare.status is None
    assert bare.detail is None


def test_a_supabase_rejection_answers_401_and_never_500(monkeypatch, fresh_client, capsys):
    client, _settings = fresh_client

    started = client.get("/app/auth/supabase/login")
    assert started.status_code == 303
    state = client.cookies["supabase_oauth_state"]
    client.cookies.set("supabase_oauth_verifier", "fresh-verifier")

    async def rejecting_exchange(*args):
        raise SupabaseAuthError(
            "Supabase authorization code exchange failed",
            status=401,
            detail="Invalid API key",
        )

    monkeypatch.setattr(router, "exchange_code", rejecting_exchange)
    callback = client.get("/app/auth/supabase/callback?code=one-use-code&state=" + state)

    assert callback.status_code == 401
    assert callback.text == "Sign-in could not be verified."

    logged = capsys.readouterr().out
    assert "'event_type': 'supabase_auth_error'" in logged
    assert "'status': 401" in logged
    assert "'detail': 'Invalid API key'" in logged
