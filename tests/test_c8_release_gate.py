"""
Helix Prime Codex C8 — release gate, profiles, manifest, backup/restore,
security, observability, and verification harness tests.

All tests are deterministic and isolated (temp state); they never mutate the
live shared control-plane/audit DBs.
"""
from __future__ import annotations

import json
import os
import tempfile

import pytest

from release import backup, harness, manifest, observability, profiles, security_gate


# ── profiles / classification ──────────────────────────────────────────────

def test_never_emits_bare_production():
    # Even when everything is green, production adds production-only gates that
    # are not satisfied, so bare PRODUCTION is impossible.
    result = profiles.classify_from_gate_results(
        "production", profiles.GATE_NAMES, release_approved=True
    )
    assert "PRODUCTION" not in result or result == "PRODUCTION"
    # With the production profile, extra gates are missing -> NOT_READY.
    assert result == "NOT_READY"


def test_production_candidate_when_all_gates_green():
    result = profiles.classify_from_gate_results(
        "production_candidate", profiles.GATE_NAMES, release_approved=True
    )
    assert result == "PRODUCTION_CANDIDATE"


def test_controlled_pilot_when_all_gates_green():
    result = profiles.classify_from_gate_results(
        "controlled_pilot", profiles.GATE_NAMES, release_approved=True
    )
    assert result == "CONTROLLED_PILOT_READY"


def test_fail_closed_on_red_gate():
    green = [g for g in profiles.GATE_NAMES if g != "security_checks"]
    result = profiles.classify_from_gate_results(
        "production_candidate", green, release_approved=True
    )
    assert result == "NOT_READY"


def test_profiles_yaml_mirror():
    data = profiles.load_profiles()
    assert set(data.get("gates", [])) == set(profiles.GATE_NAMES)
    assert "production_candidate" in data.get("profiles", [])
    assert "production" in data.get("profiles", [])


# ── manifest ───────────────────────────────────────────────────────────────

def test_manifest_required_fields():
    m = manifest.build_manifest(classification="PRODUCTION_CANDIDATE")
    for key in ["product", "release_profile", "classification", "git_commit",
                "dependency_lock_ref", "enabled_capabilities",
                "disabled_capabilities", "data_schema_versions",
                "known_limitations", "evidence_refs"]:
        assert key in m
    assert m["product"] == "Helix-Prime-Codex"
    assert "cloud_deployment" in m["disabled_capabilities"]
    assert m["classification"] == "PRODUCTION_CANDIDATE"


def test_dependency_lock_present():
    p = manifest.ROOT / "release" / "requirements.lock.txt"
    assert p.exists()
    assert p.stat().st_size > 0


# ── backup / restore / rollback ────────────────────────────────────────────

def _make_synthetic_state():
    work = tempfile.mkdtemp(prefix="hp_test_")
    from control_plane.store import Store
    from control_plane.workflow import Workflow
    from contracts.task import CorrelationContext
    db = os.path.join(work, "control_plane", "workflow.db")
    store = Store(db_path=db)
    corr = CorrelationContext(correlation_id="corr-1", idempotency_key="k-1",
                              tenant_id="t1", client_id="c1", created_at="2026-01-01T00:00:00Z")
    wf = Workflow(workflow_id="wf-1", idempotency_key="k-1", correlation=corr,
                  tenant_id="t1", client_id="c1", requesting_actor="suby",
                  owning_role_id="cadence_suby", capability="wfm_forecast",
                  state="proposed", input_payload={"is_sample": True},
                  created_at="2026-01-01T00:00:00Z", updated_at="2026-01-01T00:00:00Z")
    store.create_workflow(wf)
    store.close()
    from security.audit import AuditTrail, AuditRecord
    trail = AuditTrail(db_path=os.path.join(work, "security", "audit.db"))
    prev = None
    for i in range(3):
        rec = AuditRecord.new(event_type="test", actor="suby", actor_type="agent",
                              decision="succeeded", previous_hash=prev)
        trail.append(rec)
        prev = rec.current_hash
    trail.close()
    return work


def test_backup_restore_verify():
    work = _make_synthetic_state()
    backup_dir = os.path.join(work, "backup")
    m = backup.backup_state(backup_dir, repo_root=work)
    assert m["captured_state"]
    restore_dir = os.path.join(work, "restored")
    report = backup.restore_state(backup_dir, restore_dir, repo_root=work, schema_ok=True)
    assert report["restore_count"] > 0
    from security.audit import AuditTrail
    t = AuditTrail(db_path=os.path.join(restore_dir, "security", "audit.db"))
    try:
        valid, msg = t.verify_chain()
    finally:
        t.close()
    assert valid


def test_restore_rejects_dirty_target():
    work = _make_synthetic_state()
    backup_dir = os.path.join(work, "backup")
    backup.backup_state(backup_dir, repo_root=work)
    dirty = os.path.join(work, "dirty")
    os.makedirs(dirty, exist_ok=True)
    with open(os.path.join(dirty, "x.txt"), "w") as f:
        f.write("occupied")
    with pytest.raises(backup.BackupError):
        backup.restore_state(backup_dir, dirty, repo_root=work, schema_ok=True)


def test_schema_compatible_fail_closed():
    ok, _ = backup.schema_compatible({"security.audit": "1.0"})
    assert ok
    ok, _ = backup.schema_compatible({"security.audit": "9.9"})
    assert not ok


def test_rollback_manifest():
    work = tempfile.mkdtemp(prefix="hp_rollback_")
    target = os.path.join(work, "release-manifest.json")
    prev = {
        "git_commit": "AAAAAAAA", "version": "0.9.0-c7",
        "classification": "PRODUCTION_CANDIDATE",
    }
    cur = {
        "git_commit": "BBBBBBBB", "version": "0.9.0-c8",
        "classification": "PRODUCTION_CANDIDATE",
    }
    backup.rollback_manifest(prev, cur, target_path=target)
    out = json.load(open(target, encoding="utf-8"))
    assert out["git_commit"] == "AAAAAAAA"
    assert "_rolled_back_from" in out


# ── security gate ──────────────────────────────────────────────────────────

def test_security_gate_all_green():
    # Scan only the release package + tests fixtures region (fast, isolated).
    res = security_gate.run_security_gate(scan_subdirs=["release"])
    assert res["all_ok"] is True


def test_deny_by_default():
    res = security_gate.check_deny_by_default()
    assert res["ok"] is True


def test_redaction_removes_secret():
    res = security_gate.check_redaction()
    assert res["ok"] is True


# ── observability ──────────────────────────────────────────────────────────

def test_observability_startup_slo():
    res = observability.measure_startup()
    assert res.get("slo_met") is True


def test_observability_readiness_required_components():
    # Ollama optional; required components must still be ready.
    rep = observability.health_report()
    assert rep["ready"] is True


# ── harness / failure / soak ───────────────────────────────────────────────

def test_harness_all_green():
    r = harness.run_harness(num_soak_workflows=3)
    assert r["all_ok"] is True
    assert r["checks"]["bounded_soak"]["no_unbounded_growth"] is True


def test_harness_components_present():
    r = harness.run_harness(num_soak_workflows=2)
    c = r["checks"]["components"]
    assert c["ok"] is True
    assert c["agent_count"] >= 9
    assert c["num_capabilities"] >= 12


def test_soak_bounded_within_limits():
    import release.harness as h
    n = h.MAX_SOAK_WORKFLOWS + 100  # exceed cap -> clamp
    r = harness.run_bounded_soak(num_workflows=n, num_events_per_workflow=1)
    assert r["workflow_count"] <= h.MAX_SOAK_WORKFLOWS
    assert r["bounded"] is True


# ── gate end-to-end ────────────────────────────────────────────────────────

def test_gate_returns_candidate_or_ready():
    from release import gate
    summary = gate.run_gate(
        profile="production_candidate", num_soak_workflows=3, write_evidence=False
    )
    assert summary["classification"] in {"PRODUCTION_CANDIDATE", "CONTROLLED_PILOT_READY"}
    assert summary["exit_code"] == 0


def test_gate_controlled_pilot_ready():
    from release import gate
    summary = gate.run_gate(
        profile="controlled_pilot", num_soak_workflows=3, write_evidence=False
    )
    assert summary["classification"] in {"CONTROLLED_PILOT_READY", "PRODUCTION_CANDIDATE"}
    assert summary["exit_code"] == 0


def test_gate_never_production():
    from release import gate
    # Requesting the production profile must never yield a bare PRODUCTION label
    # (production-only gates are not met); the gate fails closed as NOT_READY.
    summary = gate.run_gate(
        profile="production", num_soak_workflows=3, write_evidence=False
    )
    assert summary["classification"] != "PRODUCTION"
    assert summary["classification"] == "NOT_READY"
    assert summary["permitted_c8_outcome"] is False
    assert summary["exit_code"] == 1
