"""Tests for the cloud-ready, local-first boundary (Prompt 9).

Verifies: offline/local execution, safe failure on missing/unavailable cloud
services, demo reset, shutdown, restricted API, and cost-control settings.
No network; all adapters are in-memory and deterministic.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pytest

from cloud.errors import SafeFailure
from cloud.config import CloudConfig
from cloud.profile import CloudProvider, optional_cloud_services, SPEND_CONTROL_DOCS

ALL_SERVICES = {
    "database", "object_storage", "queue_event_transport", "secrets",
    "identity", "observability", "scheduled_jobs", "model_providers",
}


# --- run entirely offline / local --------------------------------------------
def test_runs_offline_local():
    p = CloudProvider.local()
    # database
    p.db.put("ns", "k", {"v": 1})
    assert p.db.get("ns", "k")["v"] == 1
    # object storage
    p.storage.put_object("b", "k", b"data")
    assert p.storage.get_object("b", "k") == b"data"
    # queue / event transport
    got = []
    p.queue.subscribe("t", got.append)
    p.queue.publish("t", {"x": 1})
    assert got == [{"x": 1}]
    # secrets
    p.secrets.set_secret("s", "v")
    assert p.secrets.get_secret("s") == "v"
    # identity
    p.identity.register("u", "tok", ["role"])
    assert p.identity.authenticate("tok") == "u"
    assert p.identity.authorize("u", "role") is True
    # observability
    p.observability.record_metric("m", 1.0)
    p.observability.log("info", "hi")
    assert "m" in p.observability.snapshot()["metrics"]
    # scheduled jobs
    p.scheduler.schedule("j", "2026-01-01T00:00:00Z", {"p": 1})
    due = p.scheduler.run_due("2026-01-02T00:00:00Z")
    assert due and due[0][0] == "j"
    # model provider (local stub, no external call)
    assert "hello" in p.models.complete("hello")
    # provider status reflects local mode
    assert p.status()["mode"] == "local"


# --- configuration with missing cloud services --------------------------------
def test_missing_cloud_service_fails_safe():
    # requesting an unimplemented (non-local) cloud service fails safely
    cfg = CloudConfig.from_dict({"cloud_services": {"database": "aws_dynamodb"}})
    with pytest.raises(SafeFailure):
        CloudProvider.build(cfg)
    # empty config builds fine (fully local, offline)
    p = CloudProvider.local()
    assert p.status()["mode"] == "local"
    # demo profile builds fine offline with only local adapters
    d = CloudProvider.demo()
    assert d.status()["synthetic_data_only"] is True


# --- safe failure conditions -------------------------------------------------
def test_safe_failure_conditions():
    # live credentials not permitted in demo
    with pytest.raises(SafeFailure):
        CloudProvider.build(CloudConfig.from_dict({"mode": "cloud_demo", "credentials": {"AWS": "x"}}))
    # non-synthetic data forbidden in this local-first build
    with pytest.raises(SafeFailure):
        CloudProvider.build(CloudConfig.from_dict({"synthetic_data_only": False}))
    # restricted operation blocked under demo profile
    p = CloudProvider.demo()
    with pytest.raises(SafeFailure):
        p.guarded_call("delete_production", 0.0)
    # shut-down provider refuses calls
    p.controller.shutdown()
    with pytest.raises(SafeFailure):
        p.guarded_call("status", 0.0)


# --- demo reset --------------------------------------------------------------
def test_demo_reset():
    p = CloudProvider.demo()
    p.db.put("ns", "k", 1)
    p.storage.put_object("b", "k", b"x")
    p.observability.record_metric("m", 5.0)
    p.controller.reset()
    assert p.db.query("ns") == {}
    assert p.storage.list_objects("b") == []
    assert p.observability.snapshot()["metrics"] == {}
    # after reset, allowed operations still work
    assert p.guarded_call("status", 0.0, lambda: "ok") == "ok"


# --- cost-control settings ---------------------------------------------------
def test_cost_control():
    cfg = CloudConfig.from_dict({"mode": "cloud_demo", "usage_limits": {"budget_usd": 0.03}})
    p = CloudProvider.build(cfg)
    for _ in range(3):
        p.guarded_call("complete_model", 0.01, lambda: None)
    assert abs(p.spend.spent - 0.03) < 1e-9
    # 4th charge would exceed budget -> blocked
    with pytest.raises(SafeFailure):
        p.guarded_call("complete_model", 0.01)


# --- restricted API ----------------------------------------------------------
def test_restricted_api_enforced():
    p = CloudProvider.demo()
    assert p.guarded_call("complete_model", 0.0, lambda: "ok") == "ok"
    with pytest.raises(SafeFailure):
        p.guarded_call("manage_credentials", 0.0)


# --- shutdown + status -------------------------------------------------------
def test_shutdown_and_status():
    p = CloudProvider.local()
    assert p.status()["stopped"] is False
    p.controller.shutdown()
    assert p.status()["stopped"] is True
    with pytest.raises(SafeFailure):
        p.guarded_call("status", 0.0)


# --- demo profile shape ------------------------------------------------------
def test_demo_profile_shape():
    cfg = CloudConfig.from_dict({"mode": "cloud_demo"}).resolve()
    assert cfg.synthetic_data_only is True
    assert cfg.restricted_api is True
    assert cfg.credentials == {}
    assert cfg.usage_limits.budget_usd > 0
    assert "reset" in cfg.allowed_operations
    assert "shutdown" in cfg.allowed_operations
    assert SPEND_CONTROL_DOCS.strip()  # spend-control documentation present


# --- optional cloud services documented --------------------------------------
def test_optional_cloud_services_documented():
    svcs = optional_cloud_services()
    names = {s["service"] for s in svcs}
    assert names == ALL_SERVICES
    for s in svcs:
        assert s["optional"] is True
        assert s["justified_when"]
