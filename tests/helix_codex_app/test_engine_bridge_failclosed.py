"""Engine bridge fail-closed tests (P4.4 close-out).

Prove the bridge rule in one place: when the engine raises, the bridge
raises, and an empty result is never returned. The bridge has exactly three
failure modes — the engine cannot be imported, the engine run reports an
error, and the run returns no staffing figure — and each must raise
EngineUnavailableError. A healthy run must still return a full figure.
Failures are asserted with pytest.raises so a returned dict, including an
empty one, fails the test.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from helix_codex_app.errors import EngineUnavailableError
from helix_codex_app.integration.engine_bridge import WFM_OWNING_ROLE, wfm_coverage

KWARGS = {
    "tenant_id": "tenant-a",
    "client_id": "client-a",
    "correlation_id": "corr-1",
    "actor": "test",
    "from_at": "2026-09-01T00:00:00+00:00",
    "to_at": "2026-09-08T00:00:00+00:00",
}


def _coverage_result(**metrics):
    def fake_adapt(**kwargs):
        assert kwargs["owning_role_id"] == WFM_OWNING_ROLE
        return SimpleNamespace(
            error=None,
            engine_id="wfm",
            metrics=metrics,
        )

    return fake_adapt


def test_healthy_run_returns_a_full_figure(monkeypatch):
    monkeypatch.setattr(
        "engines.wfm.adapter.adapt",
        _coverage_result(optimal_agents=63, service_level_achieved=0.913),
    )
    result = wfm_coverage(**KWARGS)
    assert result["engine_id"] == "wfm"
    assert result["required_agents"] == 63
    assert result["is_sample"] is True


def test_missing_engine_raises(monkeypatch):
    monkeypatch.setitem(__import__("sys").modules, "engines.wfm.adapter", None)
    with pytest.raises(EngineUnavailableError, match="unavailable"):
        wfm_coverage(**KWARGS)


def test_engine_error_result_raises(monkeypatch):
    def fake_adapt(**kwargs):
        return SimpleNamespace(error="engine blew up", metrics=None, engine_id="wfm")

    monkeypatch.setattr("engines.wfm.adapter.adapt", fake_adapt)
    with pytest.raises(EngineUnavailableError, match="could not produce"):
        wfm_coverage(**KWARGS)


def test_missing_staffing_figure_raises(monkeypatch):
    monkeypatch.setattr("engines.wfm.adapter.adapt", _coverage_result(service_level_achieved=0.9))
    with pytest.raises(EngineUnavailableError, match="no staffing figure"):
        wfm_coverage(**KWARGS)


def test_a_raised_engine_exception_propagates(monkeypatch):
    def fake_adapt(**kwargs):
        raise RuntimeError("engine died on the job")

    monkeypatch.setattr("engines.wfm.adapter.adapt", fake_adapt)
    with pytest.raises(RuntimeError, match="engine died on the job"):
        wfm_coverage(**KWARGS)


def test_no_failure_mode_returns_an_empty_result(monkeypatch):
    sys_modules = __import__("sys").modules

    def boom(**kwargs):
        raise RuntimeError("boom")

    failures = [
        {
            "kind": "missing_engine",
            "apply": lambda: monkeypatch.setitem(sys_modules, "engines.wfm.adapter", None),
        },
        {
            "kind": "engine_error",
            "apply": lambda: monkeypatch.setattr(
                "engines.wfm.adapter.adapt",
                lambda **kw: SimpleNamespace(error="boom", metrics=None, engine_id="wfm"),
            ),
        },
        {
            "kind": "missing_figure",
            "apply": lambda: monkeypatch.setattr(
                "engines.wfm.adapter.adapt", _coverage_result(service_level_achieved=0.9)
            ),
        },
        {
            "kind": "engine_raise",
            "apply": lambda: monkeypatch.setattr("engines.wfm.adapter.adapt", boom),
        },
    ]
    for failure in failures:
        failure["apply"]()
        with pytest.raises(Exception):
            wfm_coverage(**KWARGS)
