"""The engine bridge and pack discovery (P6.1).

The bridge is the app's only door into the governed core, so these tests are
about the door, not the room: who may open it, and what happens when the room is
on fire. The rule under test is that the bridge never invents an answer. A dead
engine raises; it never returns an empty list that a screen would render as
"nothing to see".
"""
from __future__ import annotations

import pytest

from helix_codex_app.errors import EngineUnavailableError, NotFoundError, PermissionDenied
from helix_codex_app.integration import engine_bridge, packs, policy_bridge
from helix_codex_app.security.accounts import Account


def make_account(role_id: str | None, *, tenant_id: str = "tenant-a") -> Account:
    return Account(
        account_id="account-1",
        domain_id="domain-1",
        domain_name="academy.test",
        tenant_id=tenant_id,
        username="ravi",
        username_normalized="ravi",
        role_id=role_id,
        client_id="client-a",
    )


class _StubEngine:
    """A stand-in core that reports exactly the handlers it was given."""

    def __init__(self, capabilities=()) -> None:
        self.handlers = {capability: object() for capability in capabilities}


# --- the engine-facing identity ---------------------------------------------
def test_an_owner_speaks_as_the_executive():
    assert policy_bridge.to_engine_identity(make_account("owner")).role_id == "sami"


def test_a_manager_speaks_as_the_ops_gm():
    assert policy_bridge.to_engine_identity(make_account("manager")).role_id == "ops_gm"


def test_an_employee_has_no_engine_voice():
    assert policy_bridge.to_engine_identity(make_account("employee")).role_id is None


def test_a_catalog_role_passes_through_unchanged():
    assert policy_bridge.to_engine_identity(make_account("fraud_gm")).role_id == "fraud_gm"


def test_to_identity_is_unchanged_for_app_roles():
    """The P1.4 contract still holds: the app view is not the engine view."""
    assert policy_bridge.to_identity(make_account("owner")).role_id is None
    assert policy_bridge.to_identity(make_account("employee")).role_id is None


# --- who may open the door ---------------------------------------------------
def test_an_employee_is_refused_before_the_engine_is_consulted(monkeypatch):
    called = {"engine": False}

    def _never():
        called["engine"] = True
        raise AssertionError("the engine must not be reached")

    monkeypatch.setattr(engine_bridge, "_engine", _never)
    with pytest.raises(PermissionDenied):
        engine_bridge.submit_workflow(make_account("employee"), capability="wfm_forecast")
    assert called["engine"] is False


def test_a_contractor_is_refused(monkeypatch):
    with pytest.raises(PermissionDenied):
        engine_bridge.submit_workflow(make_account("contractor"), capability="wfm_forecast")


def test_a_manager_passes_authorization(monkeypatch):
    monkeypatch.setattr(engine_bridge, "_engine", lambda: _StubEngine())
    decision = policy_bridge.authorize_engine_call(
        make_account("manager"), capability="wfm_forecast", action="submit"
    )
    assert decision.allowed is True


def test_a_blank_capability_is_refused():
    with pytest.raises(PermissionDenied):
        policy_bridge.authorize_engine_call(
            make_account("manager"), capability="  ", action="submit"
        )


# --- the engine is down, or angry --------------------------------------------
def test_a_dead_engine_raises_and_never_returns_an_empty_result(monkeypatch):
    def _dead():
        raise EngineUnavailableError("the governed engine is not running")

    monkeypatch.setattr(engine_bridge, "_engine", _dead)
    with pytest.raises(EngineUnavailableError):
        engine_bridge.list_engines()
    with pytest.raises(EngineUnavailableError):
        engine_bridge.list_workflows(make_account("manager"))
    with pytest.raises(EngineUnavailableError):
        engine_bridge.list_approvals(make_account("manager"))
    with pytest.raises(EngineUnavailableError):
        engine_bridge.kill_switch_status()


def test_an_engine_that_raises_propagates(monkeypatch):
    class _Angry:
        def __init__(self) -> None:
            self.handlers: dict = {}

        @property
        def store(self):
            raise RuntimeError("the store exploded")

    monkeypatch.setattr(engine_bridge, "_engine", _Angry)
    with pytest.raises(RuntimeError):
        engine_bridge.list_workflows(make_account("manager"))


# --- engine status -----------------------------------------------------------
def test_engine_status_is_ready_when_every_capability_has_a_handler(monkeypatch):
    capabilities = engine_bridge.capability_map()["wfm"]
    monkeypatch.setattr(engine_bridge, "_engine", lambda: _StubEngine(capabilities))
    status = engine_bridge.engine_status("wfm")
    assert status["status"] == "ready"
    assert sorted(status["registered_capabilities"]) == sorted(capabilities)
    assert status["name"]


def test_engine_status_is_partial_when_a_capability_is_missing(monkeypatch):
    capabilities = engine_bridge.capability_map()["wfm"]
    monkeypatch.setattr(engine_bridge, "_engine", lambda: _StubEngine(capabilities[:-1]))
    status = engine_bridge.engine_status("wfm")
    assert status["status"] == "partial"
    assert len(status["registered_capabilities"]) == len(capabilities) - 1


def test_an_unknown_engine_is_not_found(monkeypatch):
    monkeypatch.setattr(engine_bridge, "_engine", lambda: _StubEngine())
    with pytest.raises(NotFoundError):
        engine_bridge.engine_status("not_an_engine")


def test_list_engines_covers_all_six(monkeypatch):
    capabilities = engine_bridge.capability_map()
    every = [cap for caps in capabilities.values() for cap in caps]
    monkeypatch.setattr(engine_bridge, "_engine", lambda: _StubEngine(every))
    engines = engine_bridge.list_engines()
    assert [engine["engine_id"] for engine in engines] == list(engine_bridge.ENGINE_IDS)
    assert all(engine["status"] == "ready" for engine in engines)


# --- capability packs --------------------------------------------------------
def test_pack_discovery_finds_the_sports_academy_pack():
    found = {pack["pack"]: pack for pack in packs.list_packs()}
    assert "sports_academy" in found
    academy = found["sports_academy"]
    assert academy["domain"] == "sports_academy"
    assert academy["production_readiness"] == "NOT_ESTABLISHED"
    assert academy["read_only_start"] is True
    assert academy["synthetic_data_only"] is True
    assert "Athlete" in academy["ontology"]


def test_pack_sections_are_gated_by_cockpit_view():
    sections = packs.pack_sections("sports_academy")
    keys = [section["key"] for section in sections]
    assert keys == ["owner", "coach", "parent"]
    assert all(section["required_capability"] == "cockpit.view" for section in sections)
    assert all(section["simulated_only"] is True for section in sections)


def test_every_pack_section_route_is_under_the_cockpit():
    for section in packs.all_sections():
        assert section["route"].startswith("/app/cockpit/")


def test_an_unknown_pack_is_not_found():
    with pytest.raises(NotFoundError):
        packs.pack_metadata("not_a_pack")
