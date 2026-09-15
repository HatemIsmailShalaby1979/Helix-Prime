"""The low-code capability loader: five invariants, registration, and the HTTP surface (P7.1).

The loader must refuse an invalid manifest before anything is registered, and
each invariant keeps its own typed error and its own test. The real
sports_academy manifest is the proof that a shipped pack loads and registers
its declared sections, and the administration routes are exercised through the
real app with real sessions, so "owner-only" is an HTTP answer, not a comment.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

fastapi_testclient = pytest.importorskip("fastapi.testclient")
TestClient = fastapi_testclient.TestClient

from helix_codex_app import db
from helix_codex_app.app import create_app
from helix_codex_app.config import AppSettings
from helix_codex_app.integration import packs as pack_seam
from helix_codex_app.modules.lowcode import pack_loader, section_registry
from helix_codex_app.security.accounts import AccountRepository
from helix_codex_app.security.passwords import hash_password
from helix_codex_app.security.sessions import SESSION_COOKIE, SessionStore


def _manifest(**overrides) -> dict:
    data = {
        "schema_version": "1.0",
        "id": "print_shop",
        "name": "Print Shop",
        "version": "1.0.0",
        "domain": "print_shop",
        "min_core_version": "0.9.0",
        "read_only_start": True,
        "synthetic_data_only": True,
        "production_readiness": "NOT_ESTABLISHED",
        "ontology": ["Order"],
        "sections": [
            {
                "key": "orders",
                "label": "Orders",
                "route": "/app/cockpit/owner",
                "required_capability": "cockpit.view",
            }
        ],
        "roles": [],
        "workflows": [],
        "policies": [],
        "connector_contracts": [],
        "data_classifications": ["internal"],
        "metrics": [],
        "failure_modes": [],
    }
    data.update(overrides)
    return data


def _manifest_file(tmp_path, name="print_shop.yaml", **overrides) -> Path:
    path = tmp_path / name
    path.write_text(yaml.safe_dump(_manifest(**overrides)), encoding="utf-8")
    return path


@pytest.fixture()
def ctx(tmp_path):
    db_path = str(tmp_path / "app.db")
    conn = db.connect(db_path=db_path)
    db._init_schema(conn)
    repo = AccountRepository(conn)
    domain = repo.create_domain("academy.test", tenant_id="tenant-a", client_id="client-a")
    accounts = {
        role: repo.create_account(
            domain.domain_id, role, role_id=role, password_hash=hash_password("x")
        )
        for role in ("manager", "owner", "employee")
    }
    settings = AppSettings(db_path=db_path, cookie_secure=False)
    store = SessionStore(conn, settings)
    yield SimpleNamespace(
        conn=conn,
        repo=repo,
        domain=domain,
        accounts=accounts,
        settings=settings,
        store=store,
        tmp_path=tmp_path,
    )
    db.close(conn)


@pytest.fixture()
def client(ctx, monkeypatch):
    monkeypatch.setenv("HELIX_DB_PATH", str(ctx.tmp_path / "workflow.db"))
    monkeypatch.setenv("HELIX_AUDIT_DB_PATH", str(ctx.tmp_path / "audit.db"))
    monkeypatch.setenv("HELIX_LOG_PATH", str(ctx.tmp_path / "logs.jsonl"))
    from server.config import get_settings

    get_settings.cache_clear()
    with TestClient(create_app(ctx.settings), follow_redirects=False) as test_client:
        yield test_client
    get_settings.cache_clear()


def _session(ctx, account) -> tuple[dict, dict]:
    token, _issued = ctx.store.issue_session(account)
    session = ctx.store.verify(token)
    assert session is not None
    return {SESSION_COOKIE: token}, {"X-CSRF-Token": session.csrf_token}


def test_invariant1_a_pack_role_cannot_widen_a_core_roles_financial_limit(tmp_path):
    manifest = _manifest_file(
        tmp_path,
        "widen.yaml",
        id="widen_test",
        roles=[
            {
                "id": "ops_gm",
                "owned_capabilities": ["schedule.shift"],
                "approval_limits": {"tier": "operational", "max_financial_amount": 50000},
            }
        ],
    )
    with pytest.raises(pack_loader.RoleLimitExceedsCoreError):
        pack_loader.load_pack(manifest)


def test_invariant1_a_pack_role_below_the_core_limit_loads(tmp_path):
    manifest = _manifest_file(
        tmp_path,
        "within.yaml",
        id="within_test",
        roles=[
            {
                "id": "ops_gm",
                "owned_capabilities": ["schedule.shift"],
                "approval_limits": {"tier": "operational", "max_financial_amount": 10000},
            }
        ],
    )
    pack = pack_loader.load_pack(manifest)
    assert pack.manifest.id == "within_test"


def test_invariant2_a_pack_cannot_own_a_core_capability(tmp_path):
    manifest = _manifest_file(
        tmp_path,
        "core_own.yaml",
        id="core_own_test",
        roles=[{"id": "shop_owner", "owned_capabilities": ["cockpit.view"]}],
    )
    with pytest.raises(pack_loader.CapabilityAlreadyOwnedError):
        pack_loader.load_pack(manifest)


def test_invariant2_a_pack_cannot_own_what_another_pack_owns(ctx):
    owner_a = _manifest_file(
        ctx.tmp_path,
        "owner_a.yaml",
        id="clash_owner_a",
        roles=[{"id": "shop_owner", "owned_capabilities": ["progression.score"]}],
    )
    owner_b = _manifest_file(
        ctx.tmp_path,
        "owner_b.yaml",
        id="clash_owner_b",
        roles=[{"id": "shop_owner", "owned_capabilities": ["progression.score"]}],
    )
    pack_loader.register_pack(ctx.conn, pack_loader.load_pack(owner_a))
    with pytest.raises(pack_loader.CapabilityAlreadyOwnedError):
        pack_loader.load_pack(owner_b)


def test_invariant3_live_data_mode_is_refused_below_established(tmp_path):
    manifest = _manifest_file(tmp_path, "live_low.yaml", id="live_low_test", data_mode="live")
    with pytest.raises(pack_loader.LiveDataBelowEstablishedError):
        pack_loader.load_pack(manifest)


def test_invariant3_live_data_mode_loads_once_established(tmp_path):
    manifest = _manifest_file(
        tmp_path,
        "live_ok.yaml",
        id="live_ok_test",
        data_mode="live",
        production_readiness="ESTABLISHED",
    )
    pack = pack_loader.load_pack(manifest)
    assert pack.manifest.production_readiness == "ESTABLISHED"


def test_invariant4_a_min_core_version_above_the_runtime_is_refused(tmp_path):
    manifest = _manifest_file(
        tmp_path, "newer_core.yaml", id="newer_core_test", min_core_version="0.10.0"
    )
    with pytest.raises(pack_loader.CoreVersionTooOldError):
        pack_loader.load_pack(manifest)


def test_invariant5_a_pack_role_cannot_review_its_own_action(tmp_path):
    manifest = _manifest_file(
        tmp_path,
        "self_review.yaml",
        id="self_review_test",
        workflows=[
            {
                "id": "submit_orders",
                "actor_role": "ops_clerk",
                "requires_approval_from": "ops_clerk",
            }
        ],
    )
    with pytest.raises(pack_loader.SelfReviewError):
        pack_loader.load_pack(manifest)


def test_invariant5_a_distinct_role_can_review(tmp_path):
    manifest = _manifest_file(
        tmp_path,
        "sod_ok.yaml",
        id="sod_ok_test",
        workflows=[
            {
                "id": "submit_orders",
                "actor_role": "ops_clerk",
                "requires_approval_from": "shop_owner",
            }
        ],
    )
    pack = pack_loader.load_pack(manifest)
    assert pack.workflows()[0]["requires_approval_from"] == "shop_owner"


def test_a_missing_required_key_is_a_typed_400_error(tmp_path):
    manifest = _manifest_file(tmp_path, "partial.yaml", id="partial_test")
    data = yaml.safe_load(manifest.read_text(encoding="utf-8"))
    del data["workflows"]
    manifest.write_text(yaml.safe_dump(data), encoding="utf-8")
    with pytest.raises(pack_loader.ManifestStructureError) as exc:
        pack_loader.load_pack(manifest)
    assert "workflows" in str(exc.value)


def test_a_non_semantic_version_is_refused(tmp_path):
    manifest = _manifest_file(tmp_path, "bad_version.yaml", id="bad_version_test", version="1.0")
    with pytest.raises(pack_loader.ManifestStructureError):
        pack_loader.load_pack(manifest)


def test_a_throwaway_manifest_loads_and_registers_a_section(ctx):
    manifest = _manifest_file(
        ctx.tmp_path,
        "print_shop.yaml",
        id="print_shop",
        sections=[
            {
                "key": "orders",
                "label": "Orders",
                "route": "/app/cockpit/owner",
                "required_capability": "cockpit.view",
            },
            {"key": "printdesk", "label": "Print desk", "route": "/app/work/print"},
        ],
    )
    pack = pack_loader.load_pack(manifest)
    assert pack.manifest.version == "1.0.0"
    assert pack.ontology() == {"Order": pack_loader.DeclaredEntity}

    result = pack_loader.register_pack(
        ctx.conn, pack, manifest_path=str(manifest), account=ctx.accounts["owner"]
    )
    assert result["pack"] == "print_shop"
    assert result["sections"] == ["orders", "printdesk"]

    pack_row = ctx.conn.execute(
        "SELECT * FROM capability_packs WHERE pack_id='print_shop'"
    ).fetchone()
    assert pack_row["version"] == "1.0.0"
    assert pack_row["production_readiness"] == "NOT_ESTABLISHED"
    assert pack_row["min_core_version"] == "0.9.0"
    assert pack_row["enabled"] == 1

    section = ctx.conn.execute(
        "SELECT * FROM sections WHERE section_id='print_shop:orders'"
    ).fetchone()
    assert section["key"] == "orders"
    assert section["route"] == "/app/cockpit/owner"
    assert section["required_capability"] == "cockpit.view"
    assert section["source_pack"] == "print_shop"
    assert section["position"] == 0
    assert section["enabled"] == 1

    nodes = ctx.conn.execute("SELECT * FROM nodes WHERE kind='capability_pack'").fetchall()
    assert len(nodes) == 1
    node = nodes[0]
    assert node["tenant_id"] == ctx.accounts["owner"].tenant_id
    assert node["created_by"] == ctx.accounts["owner"].account_id
    assert node["provenance_source"] == "helix_codex_app.lowcode"
    assert node["provenance_data_mode"] == "app_runtime"
    assert node["classification"] == "internal"
    assert node["nature"] == "system_event"
    assert node["correlation_id"].startswith("pack-")
    section_nodes = ctx.conn.execute("SELECT * FROM nodes WHERE kind='section'").fetchall()
    assert [node["correlation_id"].startswith("section-") for node in section_nodes]
    assert len(section_nodes) == 2

    granted = section_registry.sections_for_permissions(ctx.conn, frozenset({"cockpit.view"}))
    assert [section["key"] for section in granted] == ["orders", "printdesk"]
    assert all(section["simulated_only"] is True for section in granted)
    empty = section_registry.sections_for_permissions(ctx.conn, frozenset())
    assert [section["key"] for section in empty] == ["printdesk"]


def test_the_real_sports_academy_manifest_loads_and_registers_its_sections(client, ctx):
    manifest_path = pack_seam.pack_manifest_path("sports_academy")
    assert manifest_path.is_file()
    pack = pack_loader.load_pack(manifest_path)
    assert pack.manifest.domain == "sports_academy"
    pack_loader.register_pack(
        ctx.conn, pack, manifest_path=str(manifest_path), account=ctx.accounts["owner"]
    )

    manager_cookies, _ = _session(ctx, ctx.accounts["manager"])
    employee_cookies, _ = _session(ctx, ctx.accounts["employee"])

    response = client.get("/app/api/sections", cookies=manager_cookies)
    assert response.status_code == 200
    sections = response.json()["sections"]
    assert {section["key"] for section in sections} == {"owner", "coach"}
    assert all(section["required_capability"] == "cockpit.view" for section in sections)
    assert all(section["simulated_only"] is True for section in sections)
    assert all(section["pack"] == "sports_academy" for section in sections)

    response = client.get("/app/api/sections", cookies=employee_cookies)
    assert response.status_code == 200
    assert response.json()["sections"] == []

    for route in ("/app/cockpit/owner", "/app/cockpit/coach"):
        response = client.get(route, cookies=employee_cookies)
        assert response.status_code == 403, f"{route} returned {response.status_code}"

    response = client.get("/app/cockpit/owner", cookies=manager_cookies)
    assert response.status_code == 200


def test_sections_admin_is_owner_only_and_csrf_gated(client, ctx):
    employee_cookies, employee_headers = _session(ctx, ctx.accounts["employee"])
    manager_cookies, manager_headers = _session(ctx, ctx.accounts["manager"])
    owner_cookies, owner_headers = _session(ctx, ctx.accounts["owner"])

    response = client.post(
        "/app/admin/sections",
        json={"pack": "sports_academy"},
        cookies=employee_cookies,
        headers=employee_headers,
    )
    assert response.status_code == 403

    response = client.post(
        "/app/admin/sections",
        json={"pack": "sports_academy"},
        cookies=manager_cookies,
        headers=manager_headers,
    )
    assert response.status_code == 403

    response = client.post(
        "/app/admin/sections", json={"pack": "sports_academy"}, cookies=owner_cookies
    )
    assert response.status_code == 403

    response = client.post(
        "/app/admin/sections",
        json={"pack": "sports_academy"},
        cookies=owner_cookies,
        headers=owner_headers,
    )
    assert response.status_code == 201
    assert response.json()["pack"] == "sports_academy"
    assert set(response.json()["sections"]) == {"owner", "coach"}

    row = ctx.conn.execute(
        "SELECT * FROM capability_packs WHERE pack_id='sports_academy'"
    ).fetchone()
    assert row is not None
    assert row["version"] == "1.0.0"
    assert row["production_readiness"] == "NOT_ESTABLISHED"

    response = client.post(
        "/app/admin/sections",
        json={"pack": "no_such_pack"},
        cookies=owner_cookies,
        headers=owner_headers,
    )
    assert response.status_code == 404


def test_packs_reload_is_owner_only_and_registers_the_manifest_packs(client, ctx):
    manager_cookies, manager_headers = _session(ctx, ctx.accounts["manager"])
    response = client.post(
        "/app/admin/packs/reload", cookies=manager_cookies, headers=manager_headers
    )
    assert response.status_code == 403

    owner_cookies, owner_headers = _session(ctx, ctx.accounts["owner"])
    response = client.post("/app/admin/packs/reload", cookies=owner_cookies, headers=owner_headers)
    assert response.status_code == 201
    body = response.json()
    assert body["registered"] == ["sports_academy"]
    assert body["section_count"] == 2
    assert body["skipped"] == ["restaurant"]

    response = client.get("/app/api/packs", cookies=owner_cookies)
    assert response.status_code == 200
    packs = response.json()["packs"]
    assert [pack["pack_id"] for pack in packs] == ["sports_academy"]
    assert packs[0]["production_readiness"] == "NOT_ESTABLISHED"
    assert packs[0]["enabled"] == 1


def test_the_lowcode_surface_is_behind_the_guard(client):
    for route in ("/app/api/sections", "/app/api/packs"):
        response = client.get(route)
        assert response.status_code in (401, 403), f"{route} returned {response.status_code}"
    response = client.post("/app/admin/sections", json={"pack": "sports_academy"})
    assert response.status_code in (401, 403)
