"""App release gates and the app_pilot profile (P7.2).

Proves the six app gates hold at head and can fail when their condition is
broken, via a temporary fixture (monkeypatch). Verifies the app_pilot
profile wires correctly and classifies to CONTROLLED_PILOT_READY when all
its gates are green.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import FastAPI

from helix_codex_app.security.accounts import AccountRepository
from helix_codex_app.security.sessions import SessionStore

release_gate = pytest.importorskip("release.gate")
release_profiles = pytest.importorskip("release.profiles")


# ── profile wiring ──────────────────────────────────────────────────────────


def test_app_pilot_profile_is_known() -> None:
    assert "app_pilot" in release_profiles.PROFILE_ORDER


def test_app_pilot_profile_all_green_classifies() -> None:
    app_gates = release_profiles.PROFILE_REQUIRED_GATES["app_pilot"]
    result = release_profiles.classify_from_gate_results(
        "app_pilot", list(app_gates), release_approved=False
    )
    assert result == "CONTROLLED_PILOT_READY"


def test_app_pilot_profile_red_gate_denied() -> None:
    app_gates = list(release_profiles.PROFILE_REQUIRED_GATES["app_pilot"])
    green = [g for g in app_gates if g != "app_auth_boundary"]
    result = release_profiles.classify_from_gate_results("app_pilot", green, release_approved=False)
    assert result == "NOT_READY"


def test_app_pilot_matches_yaml_mirror() -> None:
    data = release_profiles.load_profiles()
    assert "app_pilot" in data.get("profiles", [])
    yaml_gates = set(data.get("gates", []))
    py_gates = set(release_profiles.GATE_NAMES)
    assert yaml_gates == py_gates
    yaml_app = set(data.get("app_gates", []))
    py_app = set(release_profiles.APP_GATE_NAMES)
    assert yaml_app == py_app
    yaml_req = set(data.get("required_gates", {}).get("app_pilot", []))
    py_req = set(release_profiles.PROFILE_REQUIRED_GATES["app_pilot"])
    assert yaml_req == py_req
    assert set(release_profiles.APP_GATE_NAMES) <= set(
        release_profiles.PROFILE_REQUIRED_GATES["app_pilot"]
    )


def test_all_app_gates_registered_in_gate_impl() -> None:
    for name in [
        "app_auth_boundary",
        "app_session_fail_closed",
        "app_tenant_isolation",
        "app_memory_store_isolation",
        "app_migration_drift",
        "app_pwa_assets",
    ]:
        assert name in release_gate.GATE_IMPL


def test_production_profile_still_fails() -> None:
    result = release_profiles.classify_from_gate_results(
        "production", list(release_profiles.GATE_NAMES), release_approved=True
    )
    assert result == "NOT_READY"


# ── app_auth_boundary ────────────────────────────────────────────────────────


def test_app_auth_boundary_passes() -> None:
    ok, detail = release_gate._gate_app_auth_boundary()
    assert ok, detail


def test_app_auth_boundary_can_fail(monkeypatch) -> None:
    def _unguarded() -> dict:
        return {}

    def _build_broken(*_a: object, **_kw: object) -> FastAPI:
        app = FastAPI()
        app.add_api_route("/app/unguarded", _unguarded, methods=["GET"])
        return app

    monkeypatch.setattr("helix_codex_app.app.create_app", _build_broken)
    ok, detail = release_gate._gate_app_auth_boundary()
    assert not ok
    assert "/app/unguarded" in detail


# ── app_session_fail_closed ──────────────────────────────────────────────────


def test_app_session_fail_closed_passes() -> None:
    ok, detail = release_gate._gate_app_session_fail_closed()
    assert ok, detail


def test_app_session_fail_closed_can_fail(monkeypatch) -> None:
    def noop_revoke(self, session_id: str) -> None:
        pass

    monkeypatch.setattr(SessionStore, "revoke", noop_revoke)
    ok, detail = release_gate._gate_app_session_fail_closed()
    assert not ok
    assert "revoked=False" in detail


# ── app_tenant_isolation ────────────────────────────────────────────────────


def test_app_tenant_isolation_gate_passes() -> None:
    ok, detail = release_gate._gate_app_tenant_isolation()
    assert ok, detail


def test_app_tenant_isolation_gate_can_fail(monkeypatch) -> None:
    def leaky_get(self, domain_name: str, username: str) -> SimpleNamespace:
        return SimpleNamespace(account_id="fake", tenant_id="foreign", status="active")

    monkeypatch.setattr(AccountRepository, "get_account_by_login", leaky_get)
    ok, detail = release_gate._gate_app_tenant_isolation()
    assert not ok


# ── app_memory_store_isolation ──────────────────────────────────────────────


def test_app_memory_store_isolation_passes() -> None:
    ok, detail = release_gate._gate_app_memory_store_isolation()
    assert ok, detail


def test_app_memory_store_isolation_can_fail(monkeypatch, tmp_path) -> None:
    from helix_codex_app.integration.memory_bridge import AccountMemoryStore

    shared = str(tmp_path / "shared")

    def same_store(self, account: object) -> str:
        return shared

    monkeypatch.setattr(AccountMemoryStore, "resolve_store", same_store)
    ok, detail = release_gate._gate_app_memory_store_isolation()
    assert not ok


# ── app_migration_drift ────────────────────────────────────────────────────


def test_app_migration_drift_gate_can_fail(monkeypatch) -> None:
    def fake_drift() -> tuple:
        return (["drift detected"], {"store_objects": 0, "migration_objects": 0})

    monkeypatch.setattr(
        "helix_codex_app.scripts.check_app_migration_drift.check_drift",
        fake_drift,
    )
    ok, detail = release_gate._gate_app_migration_drift()
    assert not ok
    assert "errors=1" in detail


# ── app_pwa_assets ────────────────────────────────────────────────────────


def test_app_pwa_assets_passes() -> None:
    ok, detail = release_gate._gate_app_pwa_assets()
    assert ok, detail


def test_app_pwa_assets_can_fail(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(release_gate, "ROOT", tmp_path)
    ok, detail = release_gate._gate_app_pwa_assets()
    assert not ok
    assert "missing" in detail
