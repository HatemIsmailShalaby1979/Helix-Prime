"""
Helix Prime Codex C8 — release gate, profiles, manifest, backup/restore,
security, observability, and verification harness tests.

All tests are deterministic and isolated (temp state); they never mutate the
live shared control-plane/audit DBs.
"""
from __future__ import annotations

import importlib.util
import json
import os
import pathlib
import shutil
import tempfile

import pytest
import yaml

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


def _import_profiles_copy(tmp_path: pathlib.Path):
    """Import a private copy of release/profiles.py from tmp_path.

    Exercises the real import path — module body, sibling YAML, derivation — in a
    throwaway directory, so a test can edit the file the module reads without
    touching the live module or the repository.
    """
    source = pathlib.Path(profiles.__file__)
    shutil.copy(source, tmp_path / "profiles.py")
    spec = importlib.util.spec_from_file_location("_profiles_probe", tmp_path / "profiles.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _expect_unavailable(tmp_path: pathlib.Path) -> str:
    """Import a broken copy and return the refusal message.

    Matched on the exception's name, not its class object: the copy is a distinct
    module, so it raises a distinct `ReleaseProfilesUnavailableError` class. Both
    derive from RuntimeError, and asserting on the name plus the message is
    stronger than asserting on identity would be.
    """
    with pytest.raises(RuntimeError) as excinfo:
        _import_profiles_copy(tmp_path)
    assert type(excinfo.value).__name__ == "ReleaseProfilesUnavailableError"
    return str(excinfo.value)


def test_editing_the_yaml_changes_the_derived_constants(tmp_path):
    """The property that makes the file the source of truth — end to end.

    A copy of the module is imported beside an *edited* copy of the YAML, so the
    real import path runs: module body, sibling file, derivation. Removing
    `data_isolation` from `controlled_pilot` must remove it from what that module
    requires.

    Can-fail: on the previous, mirrored code this test fails. The module carried
    its own copy of the gate lists and `load_profiles()` was read only for a sanity
    count, so the edit changed nothing — which is exactly how the hazard was
    measured in AGENTS.md §18.8.
    """
    data = profiles.load_profiles()
    data["required_gates"]["controlled_pilot"] = [
        gate for gate in data["required_gates"]["controlled_pilot"] if gate != "data_isolation"
    ]
    (tmp_path / "release-profiles.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")

    edited = _import_profiles_copy(tmp_path)

    assert "data_isolation" not in edited.gates_required_for("controlled_pilot")
    # The live module did not move: a copy was edited, not a global.
    assert "data_isolation" in profiles.gates_required_for("controlled_pilot")


def test_a_missing_yaml_fails_closed_at_import(tmp_path):
    """No file, no import — rather than a silent fallback to an inline copy."""
    assert "missing" in _expect_unavailable(tmp_path)


def test_a_malformed_yaml_fails_closed_at_import(tmp_path):
    """A file that parses but is not a complete profile set is refused too."""
    (tmp_path / "release-profiles.yaml").write_text("profiles:\n  - alpha\n", encoding="utf-8")
    assert "missing keys" in _expect_unavailable(tmp_path)


def test_a_weakened_production_profile_is_refused(tmp_path):
    """production must require every C8 gate.

    Without this check a one-line edit to the file would quietly weaken the
    strongest profile in it — the failure the fail-closed reader exists to catch.
    """
    data = profiles.load_profiles()
    data["required_gates"]["production"] = [
        gate for gate in data["required_gates"]["production"] if gate != "release_approval"
    ]
    (tmp_path / "release-profiles.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")
    message = _expect_unavailable(tmp_path)
    assert "production omits C8 gates" in message
    assert "release_approval" in message


def test_module_constants_are_the_canonical_files_values():
    """There is no second copy: the constants *are* the derivation of the file.

    The mirror test this replaced compared two copies and was only ever as good
    as the discipline of keeping them in step. This asserts the structural
    property instead, so re-introducing a hardcoded copy fails here.
    """
    derived = profiles.derive_profiles(profiles.load_profiles())
    assert profiles.PROFILE_ORDER == derived["order"]
    assert profiles.GATE_NAMES == derived["gate_names"]
    assert profiles.APP_GATE_NAMES == derived["app_gate_names"]
    assert profiles.PRODUCTION_ONLY_GATES == derived["production_only_gates"]
    assert profiles.PROFILE_REQUIRED_GATES == derived["required_gates"]
    assert set(profiles.ALLOWED_FINAL_CLASSIFICATIONS) == set(derived["allowed_final"])
    assert profiles.DEFAULT_C8_CLASSIFICATION == derived["default_c8"]


def test_derived_values_match_the_hardcoded_ones_they_replaced():
    """Equivalence with the code this replaced, transcribed rather than trusted.

    These are the module's previous inline constants. The refactor's only claim is
    that deriving them from the file changed nothing, so the assertion is exact
    equality — lists in order, not "roughly the same set".
    """
    c8 = [
        "repository_state",
        "reproducible_install",
        "configuration_validation",
        "dependency_locking",
        "startup_readiness",
        "backup_restore",
        "rollback",
        "data_isolation",
        "audit_integrity",
        "security_checks",
        "failure_recovery",
        "performance_limits",
        "operator_readiness",
        "release_approval",
    ]
    production_only = [
        "signed_production_evidence",
        "certified_data_isolation",
        "external_observer_audit",
        "production_deployment_architecture",
        "disaster_recovery_evidence",
        "operational_ownership",
        "incident_oncall_ownership",
        "security_review",
        "legal_privacy_review",
    ]
    assert profiles.GATE_NAMES == c8
    assert profiles.PRODUCTION_ONLY_GATES == production_only
    assert profiles.PROFILE_REQUIRED_GATES == {
        "alpha": ["repository_state"],
        "internal_pilot": [
            "repository_state",
            "reproducible_install",
            "configuration_validation",
            "startup_readiness",
        ],
        "controlled_pilot": c8,
        "production_candidate": c8,
        "production": c8 + production_only,
        "app_pilot": [
            "repository_state",
            "configuration_validation",
            "startup_readiness",
            "data_isolation",
            "audit_integrity",
            "app_auth_boundary",
            "app_session_fail_closed",
            "app_tenant_isolation",
            "app_memory_store_isolation",
            "app_migration_drift",
            "app_pwa_assets",
        ],
    }
    assert set(profiles.ALLOWED_FINAL_CLASSIFICATIONS) == {
        "CONTROLLED_PILOT_READY",
        "PRODUCTION_CANDIDATE",
    }
    assert profiles.DEFAULT_C8_CLASSIFICATION == "PRODUCTION_CANDIDATE"


# ── manifest ───────────────────────────────────────────────────────────────


def test_manifest_required_fields():
    m = manifest.build_manifest(classification="PRODUCTION_CANDIDATE")
    for key in [
        "product",
        "release_profile",
        "classification",
        "git_commit",
        "dependency_lock_ref",
        "enabled_capabilities",
        "disabled_capabilities",
        "data_schema_versions",
        "known_limitations",
        "evidence_refs",
    ]:
        assert key in m
    assert m["product"] == "Helix-Prime-Codex"
    assert "cloud_deployment" in m["disabled_capabilities"]
    assert m["classification"] == "PRODUCTION_CANDIDATE"


def test_manifest_schema_accepts_every_profile_and_classification_the_code_can_produce():
    """The schema used to be narrower than the code, so a real manifest failed it.

    The committed `release/release-manifest.json` carries
    `release_profile: "app_pilot"`, and the schema's enum omitted both `app_pilot`
    and `production`. It also omitted `NOT_READY` and the two values
    `classify_from_gate_results` returns for `alpha` / `internal_pilot` (it returns
    the profile name itself). Nothing validated the file, so it sat there invalid.

    The expectations are **derived from `profiles`** rather than restated here, so
    a profile or classification added to the code cannot silently outrun the
    schema. Equality, not containment: an enum entry the code cannot produce is
    drift in the other direction and is just as much a defect.
    """
    import jsonschema

    schema = json.loads(
        (manifest.ROOT / "release" / "manifest.schema.json").read_text(encoding="utf-8")
    )
    profile_enum = set(schema["properties"]["release_profile"]["enum"])
    classification_enum = set(schema["properties"]["classification"]["enum"])

    assert profile_enum == set(profiles.PROFILE_ORDER)

    produced = {manifest.build_manifest()["classification"]}  # the pre-run default
    for profile in profiles.PROFILE_ORDER:
        for green in (list(profiles.PROFILE_REQUIRED_GATES[profile]), []):
            produced.add(profiles.classify_from_gate_results(profile, green, release_approved=True))
    assert classification_enum == produced

    # And the file that actually ships must satisfy the schema it claims to.
    committed = json.loads(
        (manifest.ROOT / "release" / "release-manifest.json").read_text(encoding="utf-8")
    )
    jsonschema.validate(committed, schema)


def test_dependency_lock_present():
    p = manifest.ROOT / "release" / "requirements.lock.txt"
    assert p.exists()
    assert p.stat().st_size > 0


# ── backup / restore / rollback ────────────────────────────────────────────


def _make_synthetic_state():
    work = tempfile.mkdtemp(prefix="hp_test_")
    from contracts.task import CorrelationContext
    from control_plane.store import Store
    from control_plane.workflow import Workflow

    db = os.path.join(work, "control_plane", "workflow.db")
    store = Store(db_path=db)
    corr = CorrelationContext(
        correlation_id="corr-1",
        idempotency_key="k-1",
        tenant_id="t1",
        client_id="c1",
        created_at="2026-01-01T00:00:00Z",
    )
    wf = Workflow(
        workflow_id="wf-1",
        idempotency_key="k-1",
        correlation=corr,
        tenant_id="t1",
        client_id="c1",
        requesting_actor="suby",
        owning_role_id="cadence_suby",
        capability="wfm_forecast",
        state="proposed",
        input_payload={"is_sample": True},
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-01T00:00:00Z",
    )
    store.create_workflow(wf)
    store.close()
    from security.audit import AuditRecord, AuditTrail

    trail = AuditTrail(db_path=os.path.join(work, "security", "audit.db"))
    prev = None
    for _ in range(3):
        rec = AuditRecord.new(
            event_type="test",
            actor="suby",
            actor_type="agent",
            decision="succeeded",
            previous_hash=prev,
        )
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
        "git_commit": "AAAAAAAA",
        "version": "0.9.0-c7",
        "classification": "PRODUCTION_CANDIDATE",
    }
    cur = {
        "git_commit": "BBBBBBBB",
        "version": "0.9.0-c8",
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

    summary = gate.run_gate(profile="controlled_pilot", num_soak_workflows=3, write_evidence=False)
    assert summary["classification"] in {"CONTROLLED_PILOT_READY", "PRODUCTION_CANDIDATE"}
    assert summary["exit_code"] == 0


def test_gate_never_production():
    from release import gate

    # Requesting the production profile must never yield a bare PRODUCTION label
    # (production-only gates are not met); the gate fails closed as NOT_READY.
    summary = gate.run_gate(profile="production", num_soak_workflows=3, write_evidence=False)
    assert summary["classification"] != "PRODUCTION"
    assert summary["classification"] == "NOT_READY"
    assert summary["permitted_c8_outcome"] is False
    assert summary["exit_code"] == 1
