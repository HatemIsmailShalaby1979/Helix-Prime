"""Rate limits on the routes a stranger can reach, and the address they key on.

Three things are worth proving, and the third is the one that decides whether the
first two are useful:

1. THE CEILING IS REAL. Past a route's ceiling the next request answers 429 with
   the app's typed ``limit_exceeded`` code, on the public sign-in routes and on the
   demo routes alike.
2. THE KEY IS THE VISITOR, NOT THE TUNNEL. The app is loopback-bound, so the socket
   peer is the tunnel's own local connection and is identical for every visitor.
   The resolver must prefer the header the Worker sets, then the edge header, and
   only then the peer.
3. A NORMAL VISIT DOES NOT TRIP IT. These ceilings bound abuse; a single person
   using the demo must not be able to feel them. A limit that fires on ordinary
   use is a worse defect than no limit, because it is visible to the customer.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from starlette.requests import Request

TestClient = pytest.importorskip("fastapi.testclient").TestClient

from helix_codex_app import db
from helix_codex_app.app import create_app
from helix_codex_app.config import AppSettings
from helix_codex_app.errors import LimitExceeded
from helix_codex_app.security.accounts import (
    DEMO_CLIENT_ID,
    DEMO_DOMAIN_NAME,
    DEMO_TENANT_ID,
    AccountRepository,
    ensure_demo_account,
)
from helix_codex_app.security.client_ip import client_ip
from helix_codex_app.security.passwords import hash_password
from helix_codex_app.security.route_limits import (
    SUPABASE_LOGIN,
    WFM_DEMO_SCREEN,
    WFM_DEMO_SUBMIT,
    RouteLimit,
    RouteThrottle,
)
from helix_codex_app.security.sessions import SESSION_COOKIE, SessionStore

SCREEN_PATH = "/app/ops/demo"
SUBMIT_PATH = "/app/api/ops/demo/wfm"
GOOD = {"arrival_rate": 12.5, "average_handling_time": 6.0, "service_level_target": 0.8}


def _request(headers: dict[str, str], peer: str = "127.0.0.1") -> Request:
    raw = [(k.lower().encode(), v.encode()) for k, v in headers.items()]
    return Request(
        {"type": "http", "headers": raw, "client": (peer, 51000), "method": "GET", "path": "/"}
    )


def test_the_workers_header_wins_over_the_edge_header():
    """The Worker hop rewrites cf-connecting-ip, so its own header must lead."""
    seen = client_ip(
        _request(
            {
                "x-helix-client-ip": "203.0.113.9",
                "cf-connecting-ip": "2a06:98c0:3600::103",
            }
        )
    )
    assert seen == "203.0.113.9"


def test_the_edge_header_is_used_when_no_worker_set_one():
    """The tunnel-direct path has no Worker in front of it."""
    assert client_ip(_request({"cf-connecting-ip": "198.51.100.4"})) == "198.51.100.4"


def test_the_socket_peer_is_the_last_resort():
    assert client_ip(_request({}, peer="127.0.0.1")) == "127.0.0.1"


def test_a_value_that_is_not_an_address_is_ignored():
    """A junk header must not become a bucket key."""
    assert client_ip(_request({"x-helix-client-ip": "not-an-ip"})) == "127.0.0.1"
    assert (
        client_ip(_request({"x-helix-client-ip": "not-an-ip", "cf-connecting-ip": "198.51.100.4"}))
        == "198.51.100.4"
    )


def test_the_throttle_counts_then_refuses(tmp_path):
    conn = db.connect(db_path=str(tmp_path / "throttle.db"))
    db._init_schema(conn)
    try:
        throttle = RouteThrottle(conn)
        limit = RouteLimit("unit.test", 2, 60)
        throttle.check(limit, "203.0.113.9")
        throttle.check(limit, "203.0.113.9")
        with pytest.raises(LimitExceeded) as raised:
            throttle.check(limit, "203.0.113.9")
        assert raised.value.status_code == 429
        assert raised.value.code == "limit_exceeded"
        assert raised.value.payload["limit"] == "unit.test"

        throttle.check(limit, "203.0.113.10")
        assert throttle.count("route:unit.test:ip:203.0.113.9") == 2
        assert throttle.count("route:unit.test:ip:203.0.113.10") == 1
    finally:
        db.close(conn)


@pytest.fixture()
def supabase_client(tmp_path):
    settings = AppSettings(
        db_path=str(tmp_path / "limits.db"),
        cookie_secure=False,
        supabase_url="https://project.supabase.co",
        supabase_anon_key="publishable-test-key",
        supabase_redirect_uri="https://app.example.test/app/auth/supabase/callback",
    )
    with TestClient(create_app(settings), follow_redirects=False) as client:
        yield client


def test_the_sign_in_entry_refuses_past_its_ceiling(supabase_client):
    for _ in range(SUPABASE_LOGIN.max_requests):
        assert supabase_client.get("/app/auth/supabase/login").status_code == 303

    refused = supabase_client.get("/app/auth/supabase/login")

    assert refused.status_code == 429
    assert refused.json()["error"]["code"] == "limit_exceeded"
    assert refused.json()["error"]["payload"]["limit"] == SUPABASE_LOGIN.name


def test_a_normal_sign_in_never_trips_a_limit(supabase_client):
    """One person clicking the button a few times is not abuse."""
    assert supabase_client.get("/app/auth/login").status_code == 200
    for _ in range(3):
        assert supabase_client.get("/app/auth/supabase/login").status_code == 303


@pytest.fixture()
def demo_ctx(tmp_path):
    db_path = str(tmp_path / "app.db")
    conn = db.connect(db_path=db_path)
    db._init_schema(conn)
    repo = AccountRepository(conn)
    repo.create_domain(DEMO_DOMAIN_NAME, tenant_id=DEMO_TENANT_ID, client_id=DEMO_CLIENT_ID)
    demo = ensure_demo_account(repo, password_hash=hash_password("x"))
    settings = AppSettings(db_path=db_path, cookie_secure=False)
    yield SimpleNamespace(
        conn=conn, demo=demo, settings=settings, store=SessionStore(conn, settings)
    )
    db.close(conn)


@pytest.fixture()
def demo_client(demo_ctx, monkeypatch):
    monkeypatch.setenv("HELIX_DB_PATH", str(demo_ctx.settings.db_path) + "-workflow")
    monkeypatch.setenv("HELIX_AUDIT_DB_PATH", str(demo_ctx.settings.db_path) + "-audit")
    monkeypatch.setenv("HELIX_LOG_PATH", str(demo_ctx.settings.db_path) + "-logs.jsonl")
    from server.config import get_settings

    get_settings.cache_clear()
    with TestClient(create_app(demo_ctx.settings), follow_redirects=False) as test_client:
        yield test_client
    get_settings.cache_clear()


def _session(ctx) -> tuple[dict, dict]:
    token, _issued = ctx.store.issue_session(ctx.demo)
    session = ctx.store.verify(token)
    assert session is not None
    return {SESSION_COOKIE: token}, {"X-CSRF-Token": session.csrf_token}


def test_the_demo_screen_refuses_past_its_ceiling(demo_ctx, demo_client):
    cookies, _headers = _session(demo_ctx)
    for _ in range(WFM_DEMO_SCREEN.max_requests):
        assert demo_client.get(SCREEN_PATH, cookies=cookies).status_code == 200

    refused = demo_client.get(SCREEN_PATH, cookies=cookies)

    assert refused.status_code == 429
    assert refused.json()["error"]["code"] == "limit_exceeded"
    assert refused.json()["error"]["payload"]["limit"] == WFM_DEMO_SCREEN.name


def test_a_normal_visit_never_trips_a_limit(demo_ctx, demo_client):
    """One person: open the screen, submit twice, look at the result. Nothing refuses."""
    cookies, headers = _session(demo_ctx)

    assert demo_client.get(SCREEN_PATH, cookies=cookies).status_code == 200
    for _ in range(2):
        submitted = demo_client.post(SUBMIT_PATH, cookies=cookies, headers=headers, json=GOOD)
        assert submitted.status_code == 201
        assert demo_client.get(SCREEN_PATH, cookies=cookies).status_code == 200


def test_exhausting_one_route_does_not_lock_another(demo_ctx, demo_client):
    """The bucket carries the route name, so a submit flood cannot close the screen."""
    cookies, headers = _session(demo_ctx)
    for _ in range(WFM_DEMO_SUBMIT.max_requests):
        submitted = demo_client.post(SUBMIT_PATH, cookies=cookies, headers=headers, json=GOOD)
        assert submitted.status_code == 201

    refused = demo_client.post(SUBMIT_PATH, cookies=cookies, headers=headers, json=GOOD)

    assert refused.status_code == 429
    assert refused.json()["error"]["payload"]["limit"] == WFM_DEMO_SUBMIT.name
    assert demo_client.get(SCREEN_PATH, cookies=cookies).status_code == 200
