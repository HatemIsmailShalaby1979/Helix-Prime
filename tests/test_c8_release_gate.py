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
    # `allowed_final` is the one value that has moved since this equivalence was
    # established: PRODUCTION was added on 2026-09-20 by owner decision, so the
    # label is permitted when the gates are genuinely satisfied. The assertion is
    # still kept exact rather than relaxed to a subset, so any *further* movement
    # fails here — the point of this test is to notice movement, not to allow it.
    assert set(profiles.ALLOWED_FINAL_CLASSIFICATIONS) == {
        "CONTROLLED_PILOT_READY",
        "PRODUCTION_CANDIDATE",
        "PRODUCTION",
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


def test_gate_refuses_production_without_evidence():
    from release import gate

    # Requesting the production profile with nothing declared must not yield a
    # PRODUCTION label: the nine production-only gates are red, so the gate fails
    # closed. (Renamed from `test_gate_never_production` on 2026-09-20 — the gate
    # *can* now emit PRODUCTION, but only on signed external evidence; what this
    # pins is the refusal, which is the half that must never change.)
    summary = gate.run_gate(profile="production", num_soak_workflows=3, write_evidence=False)
    assert summary["classification"] != "PRODUCTION"
    assert summary["classification"] == "NOT_READY"
    assert summary["permitted_c8_outcome"] is False
    assert summary["exit_code"] == 1


def test_production_is_permitted_only_on_signed_evidence(monkeypatch, tmp_path):
    """The label is reachable by evidence, and by nothing else.

    Before 2026-09-20 this same run went 23/23 gates green, classified
    `PRODUCTION`, and still exited 1 — a sprint-policy refusal sitting on top of
    the gates. `allowed_final` now permits the label, which makes the gates the
    *only* thing standing in the way; they need signatures from a key that is not
    in this repository. Both halves are asserted in one test so neither can pass
    vacuously: with no evidence the gate must refuse, with the nine signed
    artifacts it must permit. The fixtures are synthetic and the key is a
    throwaway, so this proves the mechanism, not an approval.
    """
    from release import gate

    fixtures = pathlib.Path(__file__).parent / "fixtures" / "production_evidence"

    # Half one: nothing declared -> refused, and no label claimed.
    monkeypatch.delenv("HELIX_PRODUCTION_EVIDENCE_DIR", raising=False)
    monkeypatch.delenv("HELIX_PRODUCTION_EVIDENCE_PUBKEY", raising=False)
    summary = gate.run_gate(profile="production", num_soak_workflows=3, write_evidence=False)
    assert summary["classification"] == "NOT_READY"
    assert summary["permitted_c8_outcome"] is False
    assert summary["exit_code"] == 1

    # Half two: the nine signed artifacts are the only difference.
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    for artifact in fixtures.glob("*.evidence.json"):
        shutil.copy(artifact, evidence / artifact.name)
        shutil.copy(
            artifact.with_suffix(artifact.suffix + ".sig"),
            evidence / (artifact.name + ".sig"),
        )
    monkeypatch.setenv("HELIX_PRODUCTION_EVIDENCE_DIR", str(evidence))
    monkeypatch.setenv("HELIX_PRODUCTION_EVIDENCE_PUBKEY", str(fixtures / "test_pub.pem"))

    summary = gate.run_gate(profile="production", num_soak_workflows=3, write_evidence=False)
    assert summary["all_gates_green"] is True
    assert summary["classification"] == "PRODUCTION"
    assert summary["permitted_c8_outcome"] is True
    assert summary["exit_code"] == 0


# ── individual gates ───────────────────────────────────────────────────────


def test_repository_state_gate_refuses_when_the_commit_is_not_attestable(monkeypatch):
    """This gate used to be vacuous, and reported a condition it never checked.

    It called `build_manifest()` for its side effect and then returned `True`
    unconditionally, so it was green even with git undetectable — while reporting
    "git + runtime detectable". Nothing could fail, because `build_manifest()`
    degrades to `git_commit: "unknown"` rather than raising. Measured before the
    fix: `(True, 'repository_state: git + runtime detectable')` alongside a
    manifest saying `git_commit: unknown`.

    A release that cannot name its commit cannot be attested, so it now refuses.
    This is the section 18.2 A0.1 class: a control the ledger described as active
    that could never fire.
    """
    from release import gate

    monkeypatch.setattr(manifest, "_git_head", lambda: None)
    monkeypatch.setattr(manifest, "_git_branch", lambda: None)

    ok, reason = gate.GATE_IMPL["repository_state"]()
    assert ok is False
    assert "not detectable" in reason
    # The gate is reading the value that actually matters, not a proxy for it.
    assert manifest.build_manifest()["git_commit"] == "unknown"


def test_repository_state_gate_is_green_in_a_real_checkout():
    from release import gate

    ok, reason = gate.GATE_IMPL["repository_state"]()
    assert ok is True
    assert "git + runtime detectable" in reason


def test_repository_state_gate_does_not_claim_repo_cleanliness():
    """Its declared purpose used to be "clean-ish repo, reproducible commands present".

    Neither was ever checked, and the second cannot be: running the gate writes
    `release/release-manifest.json`, so the tree is dirty immediately afterwards by
    construction. The purpose is now stated as attestability, and this pins that the
    reason string does not re-acquire a cleanliness claim.
    """
    from release import gate

    _ok, reason = gate.GATE_IMPL["repository_state"]()
    assert "clean" not in reason.lower()
    assert "attest" in gate.GATE_IMPL["repository_state"].__doc__.lower()


def _lock_tree(tmp_path, lock_body, setup_doc="# Setup\nsee release/requirements.lock.txt\n"):
    """A temp repo root holding only what the two lock gates read.

    `monkeypatch.setattr(gate, "ROOT", ...)` is what makes this work: both gates
    read the module global at call time, so a probe never touches the real tree.
    The setup document is *removed* when `setup_doc` is None, so a second call in
    one test cannot silently inherit the first call's file.
    """
    (tmp_path / "release").mkdir(parents=True, exist_ok=True)
    (tmp_path / "release" / "requirements.lock.txt").write_text(lock_body, encoding="utf-8")
    doc = tmp_path / "docs" / "release" / "setup-guide.md"
    if setup_doc is None:
        if doc.exists():
            doc.unlink()
    else:
        doc.parent.mkdir(parents=True, exist_ok=True)
        doc.write_text(setup_doc, encoding="utf-8")
    return tmp_path


def test_reproducible_install_counts_declarations_not_indented_comments(monkeypatch, tmp_path):
    """It reported 337 "declared deps" for a lock file holding 120.

    The filter was `not ln.startswith("#")`, which does not strip leading
    whitespace — and pip-compile *indents* its `# via ...` provenance comments. So
    217 comments were counted as dependencies, and a lock file containing nothing
    but an indented comment passed the gate. This is the §18.2 A0.1 class: a
    control reporting a quantity it never measured.
    """
    from release import gate

    # The real file: the count is now the number of real pins.
    ok, reason = gate.GATE_IMPL["reproducible_install"]()
    assert ok is True
    assert "120 declared deps" in reason
    assert "337" not in reason

    # Can-fail: a lock file whose only line is an indented comment declares
    # nothing, and must not satisfy a gate about a dependency set.
    monkeypatch.setattr(gate, "ROOT", _lock_tree(tmp_path, "    # via -r requirements.txt\n"))
    ok, reason = gate.GATE_IMPL["reproducible_install"]()
    assert ok is False
    assert "0 declared deps" in reason


def test_dependency_locking_refuses_an_unpinned_requirement(monkeypatch, tmp_path):
    """The gate checked only that the file was non-empty.

    Its declared purpose is "dependency versions pinned/locked", but a lock file
    containing the bare lines `requests` / `flask` passed, as did one containing a
    single comment. It is now strictly stronger than a file-existence check, which
    it needed to be: before this fix it was *weaker* than `reproducible_install`,
    so it could never be the gate that failed.
    """
    from release import gate

    for body, expect in (
        ("requests\n", "unpinned"),
        ("requests>=2.0\n", "unpinned"),
        ("-r requirements.txt\n", "unpinned"),
        ("    # nothing declared here\n", "0 pinned"),
    ):
        monkeypatch.setattr(gate, "ROOT", _lock_tree(tmp_path, body))
        ok, reason = gate.GATE_IMPL["dependency_locking"]()
        assert ok is False, f"{body!r} should not satisfy the locking gate"
        assert expect in reason

    # And a real pin set still passes.
    monkeypatch.setattr(gate, "ROOT", _lock_tree(tmp_path, "requests==2.31.0\n"))
    ok, reason = gate.GATE_IMPL["dependency_locking"]()
    assert ok is True
    assert "1 pinned" in reason


def test_the_two_lock_gates_are_not_the_same_check(monkeypatch, tmp_path):
    """Both read one file, so they must not become two copies of one rule.

    Independence in both directions, which is what stops one of them being
    redundant: a declared-but-unpinned set satisfies `reproducible_install` and
    not `dependency_locking`; a pinned set with no documented setup path does the
    reverse. Before the fix they overlapped completely and the weaker one could
    never fire.
    """
    from release import gate

    monkeypatch.setattr(gate, "ROOT", _lock_tree(tmp_path, "requests>=2.0\n"))
    assert gate.GATE_IMPL["reproducible_install"]()[0] is True
    assert gate.GATE_IMPL["dependency_locking"]()[0] is False

    monkeypatch.setattr(gate, "ROOT", _lock_tree(tmp_path, "requests==2.31.0\n", setup_doc=None))
    assert gate.GATE_IMPL["reproducible_install"]()[0] is False
    assert gate.GATE_IMPL["dependency_locking"]()[0] is True


def test_reproducible_install_requires_a_setup_document_naming_the_lock(monkeypatch, tmp_path):
    """The first half of its purpose ("one setup path documented") was never checked.

    Unlike `repository_state`'s "clean-ish repo", this clause *is* checkable — the
    document exists, is titled "Setup Guide (Reproducible Install)", and names this
    gate — so it is implemented rather than deleted from the purpose.
    """
    from release import gate

    monkeypatch.setattr(gate, "ROOT", _lock_tree(tmp_path, "requests==2.31.0\n"))
    assert gate.GATE_IMPL["reproducible_install"]()[0] is True

    # A setup document that does not name the lock is not a reproducible path.
    monkeypatch.setattr(
        gate,
        "ROOT",
        _lock_tree(tmp_path, "requests==2.31.0\n", setup_doc="# Setup\nnothing here\n"),
    )
    ok, reason = gate.GATE_IMPL["reproducible_install"]()
    assert ok is False
    assert "setup doc=False" in reason

    # And no document at all is refused.
    monkeypatch.setattr(gate, "ROOT", _lock_tree(tmp_path, "requests==2.31.0\n", setup_doc=None))
    assert gate.GATE_IMPL["reproducible_install"]()[0] is False


def test_the_committed_setup_guide_is_the_document_the_gate_reads():
    """The gate and the document cannot drift: the guide names the file it is read from."""
    from release import gate

    doc = manifest.ROOT / gate._SETUP_DOC
    assert doc.exists()
    text = doc.read_text(encoding="utf-8")
    assert "requirements.lock.txt" in text
    assert "reproducible_install" in text
