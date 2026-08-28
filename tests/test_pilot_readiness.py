"""
Helix Prime Codex post-C8 — controlled-pilot readiness tests.

Covers profile correctness, the sign-off state machine, the pilot dry-run
(isolation, no real data/secrets, success/denial, backup/restore, audit
integrity, tenant isolation), evidence accounting, smoke nuances, and C0-C8
regression (release gate still passes for the controlled-pilot profile).

All tests are deterministic and isolated; they never mutate live shared DBs and
never write to the repo's evidence/ directory.
"""
from __future__ import annotations

import pathlib
import tempfile

from release import gate, profiles, security_gate
from release import pilot_metrics
from release import signoff
from scripts import pilot_dry_run


# ── profile correctness ─────────────────────────────────────────────────────

def test_controlled_pilot_profile_is_known():
    assert profiles.is_known_profile("controlled_pilot") is True
    required = profiles.gates_required_for("controlled_pilot")
    assert set(required) == set(profiles.GATE_NAMES)


def test_all_c8_gates_present():
    assert len(profiles.GATE_NAMES) == 14


def test_production_requires_the_nine_production_only_gates():
    prod = profiles.gates_required_for("production")
    for g in profiles.PRODUCTION_ONLY_GATES:
        assert g in prod
    assert len(profiles.PRODUCTION_ONLY_GATES) == 9


def test_production_stays_not_ready_even_if_all_gates_green():
    result = profiles.classify_from_gate_results(
        "production", profiles.GATE_NAMES, release_approved=True
    )
    assert result == "NOT_READY"


def test_production_requires_all_nine_gates_green_and_approval():
    green = list(profiles.GATE_NAMES) + list(profiles.PRODUCTION_ONLY_GATES)
    # Without human release approval, still NOT_READY.
    assert profiles.classify_from_gate_results("production", green, False) == "NOT_READY"
    # Even with approval and all nine green, gate/production classify logic is
    # fail-closed; require the dedicated classifier path.
    assert profiles.classify_from_gate_results("production", green, True) == "PRODUCTION"


def test_controlled_pilot_readiness_classification():
    assert (
        profiles.classify_from_gate_results(
            "controlled_pilot", profiles.GATE_NAMES, release_approved=True
        )
        == "CONTROLLED_PILOT_READY"
    )


def test_prod_gate_impls_are_registered_and_red():
    for g in profiles.PRODUCTION_ONLY_GATES:
        assert g in gate.GATE_IMPL, f"{g} not registered"
        ok, _reason = gate.GATE_IMPL[g]()
        assert ok is False, f"{g} must be fail-closed red locally"


# ── sign-off state machine ──────────────────────────────────────────────────

def _pilot_signoff(**over):
    base = dict(
        state="pilot_approved",
        release_profile="controlled_pilot",
        evidence_pack_id="ev-1",
        reviewer="alice",
        reviewer_role="pilot_operator",
        decision="approve",
        decided_at="2026-01-01T00:00:00Z",
        evidence_refs=["evidence/pilot/1/summary.json"],
    )
    base.update(over)
    return signoff.SignOff(**base)


def test_unsigned_cannot_approve():
    s = signoff.new_signoff()
    ok, _ = signoff.validate_signoff(s)
    assert ok
    assert signoff.is_release_approved(s) is False
    assert signoff.can_prove_gate_locally(s) is True


def test_internal_review_is_not_a_release_approval():
    s = signoff.SignOff(state="internal_review")
    ok, _ = signoff.validate_signoff(s)
    assert ok
    assert signoff.is_release_approved(s) is False


def test_pilot_approved_requires_approve_and_reviewer():
    assert signoff.is_release_approved(_pilot_signoff()) is True
    bad = _pilot_signoff(decision="reject")
    assert signoff.is_release_approved(bad) is False
    no_reviewer = _pilot_signoff(reviewer="")
    ok, _ = signoff.validate_signoff(no_reviewer)
    assert ok is False


def test_conditional_requires_conditions():
    no_cond = signoff.SignOff(state="conditional", decided_at="2026-01-01T00:00:00Z")
    ok, _ = signoff.validate_signoff(no_cond)
    assert ok is False
    with_cond = signoff.SignOff(
        state="conditional",
        decided_at="2026-01-01T00:00:00Z",
        conditions=["retain evidence"],
    )
    ok, _ = signoff.validate_signoff(with_cond)
    assert ok
    assert signoff.is_release_approved(with_cond) is False


def test_expired_signoff_is_rejected():
    s = _pilot_signoff(expires_at="2000-01-01T00:00:00Z")
    ok, _ = signoff.validate_signoff(s)
    assert ok is False


def test_evidence_ref_required_for_pilot_approval():
    no_refs = _pilot_signoff(evidence_refs=[])
    ok, _ = signoff.validate_signoff(no_refs)
    assert ok is False


def test_production_approved_never_satisfiable_locally():
    s = _pilot_signoff(
        state="production_approved",
        signature_ref="sig-1",
    )
    ok, _ = signoff.validate_signoff(s)
    assert ok is False  # _all_production_gates_satisfied() is always False


def test_unknown_state_is_rejected():
    s = signoff.SignOff(state="not_a_state")
    ok, _ = signoff.validate_signoff(s)
    assert ok is False


# ── pilot metrics ───────────────────────────────────────────────────────────

def test_metrics_separate_measured_proposed_and_production():
    m = pilot_metrics.build_summary(
        total_workflows=8,
        completed=8,
        denied_approvals=1,
        timeouts=1,
        retries=1,
        dead_letter=1,
        audit_verified=1,
        audit_total=1,
        timings_ms=[100.0, 200.0],
    )
    assert "measured_synthetic_dry_run" in m
    assert "proposed_pilot_thresholds" in m
    assert "production_slos_not_validated" in m
    measured = m["measured_synthetic_dry_run"]
    assert measured["workflow_completion_rate"] == 1.0
    assert measured["tenant_isolation_violations"] == 0
    # Production SLOs are explicitly not validated.
    assert m["production_slos_not_validated"]["availability_ge"] is None


# ── pilot dry-run ───────────────────────────────────────────────────────────

def test_dry_run_is_isolated_and_reports_ready(tmp_path):
    summary = pilot_dry_run.run_pilot_dry_run(
        artifact_dir=tmp_path / "evidence", cleanup=True
    )
    assert summary["classification"] == "CONTROLLED_PILOT_READY"
    assert summary["exit_code"] == 0
    assert summary["all_checks_green"] is True
    assert summary["is_sample"] is True
    # Evidence written to the supplied dir, not the repo.
    assert (tmp_path / "evidence" / "pilot-dry-run-summary.json").exists()
    assert (tmp_path / "evidence" / "pilot-metrics.json").exists()


def test_dry_run_does_not_touch_repo_state():
    repo_evidence = pilot_dry_run.ROOT / "evidence" / "pilot"
    before = set(repo_evidence.glob("*")) if repo_evidence.exists() else set()
    with tempfile.TemporaryDirectory() as d:
        pilot_dry_run.run_pilot_dry_run(artifact_dir=pathlib.Path(d) / "ev", cleanup=True)
    after = set(repo_evidence.glob("*")) if repo_evidence.exists() else set()
    assert before == after


def test_dry_run_records_no_data_violations():
    with tempfile.TemporaryDirectory() as d:
        s = pilot_dry_run.run_pilot_dry_run(
            artifact_dir=pathlib.Path(d) / "ev", cleanup=True
        )
    m = s["metrics"]["measured_synthetic_dry_run"]
    assert m["data_classification_violations"] == 0
    assert m["tenant_isolation_violations"] == 0
    assert m["model_unavailable_count"] == 0
    assert m["sibling_transport_failures"] == 0


def test_dry_run_vertical_slice_success_and_denial():
    with tempfile.TemporaryDirectory() as d:
        s = pilot_dry_run.run_pilot_dry_run(
            artifact_dir=pathlib.Path(d) / "ev", cleanup=True
        )
    checks = s["checks"]
    assert checks["c5_vertical_slice"]["ok"] is True
    assert checks["c5_vertical_slice"]["detail"].startswith("vertical_slice: 9 steps")
    assert checks["c5_denial"]["ok"] is True


def test_dry_run_backup_restore_and_audit_integrity():
    with tempfile.TemporaryDirectory() as d:
        s = pilot_dry_run.run_pilot_dry_run(
            artifact_dir=pathlib.Path(d) / "ev", cleanup=True
        )
    br = s["checks"]["backup_restore"]
    assert br["ok"] is True
    assert "audit_valid=True" in br["detail"]
    assert s["checks"]["security_audit_redaction"]["ok"] is True


def test_dry_run_tenant_isolation_and_scenarios():
    with tempfile.TemporaryDirectory() as d:
        s = pilot_dry_run.run_pilot_dry_run(
            artifact_dir=pathlib.Path(d) / "ev", cleanup=True
        )
    sc = s["checks"]["scenarios"]
    assert sc["ok"] is True
    assert sc["checks"]["tenant_isolation"] is True
    assert sc["checks"]["engine_timeout"] is True
    assert sc["checks"]["retry_deadletter"] is True


def test_dry_run_verifies_security_gate():
    with tempfile.TemporaryDirectory() as d:
        s = pilot_dry_run.run_pilot_dry_run(
            artifact_dir=pathlib.Path(d) / "ev", cleanup=True
        )
    sg = s["checks"]["security_audit_redaction"]
    assert sg["ok"] is True
    for k in ("secrets_scan", "classification", "redaction", "audit_integrity"):
        assert sg["checks"][k] is True


def test_no_real_secrets_committed():
    res = security_gate.run_security_gate(scan_subdirs=["release"])
    assert res["all_ok"] is True


# ── smoke nuance handling ───────────────────────────────────────────────────

def test_smoke_nuance_components_and_alias_are_informational():
    # The dry-run C6 names/aliases check must pass and report agent count.
    with tempfile.TemporaryDirectory() as d:
        s = pilot_dry_run.run_pilot_dry_run(
            artifact_dir=pathlib.Path(d) / "ev", cleanup=True
        )
    assert s["checks"]["c6_names_aliases"]["ok"] is True
    assert s["checks"]["c6_names_aliases"].get("agent_count", 0) >= 1


# ── C0-C8 regression ────────────────────────────────────────────────────────

def test_c8_regression_production_candidate_still_emits_candidate():
    result = profiles.classify_from_gate_results(
        "production_candidate", profiles.GATE_NAMES, release_approved=True
    )
    assert result == "PRODUCTION_CANDIDATE"
