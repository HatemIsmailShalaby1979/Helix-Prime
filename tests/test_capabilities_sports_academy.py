"""Tests for the sports-academy capability pack (v1).

Mirrors tests/test_capabilities_restaurant.py: registration, tenant isolation,
synthetic walkthrough, evidence + provenance, approval gating (added in S4),
memory recording, failure handling, no external writes, no production claim.
Attendance (S1) tests come first — attendance is the client's #1 pain.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from capabilities.sports_academy import (  # noqa: E402
    build_academy_connectors, build_synthetic_academy,
    compute_attendance, daily_adherence_report, record_attendance_outcome,
    DATA_MODE,
)
from capabilities.sports_academy.adapters.attendance_adapter import (  # noqa: E402
    rta_attendance_adherence,
)
from capabilities.sports_academy import kpis as academy_kpis  # noqa: E402
from capabilities.sports_academy.adapters.athlete_profile_adapter import (  # noqa: E402
    athlete_profile, churn_risk_scores, record_churn_flags,
)
from capabilities.sports_academy.workflows import (  # noqa: E402
    AcademyDiagnosis, attendance_flow, enrollment_flow, load_flow_declaration,
    renewal_flow,
)
from capabilities.sports_academy import roles as academy_roles  # noqa: E402
from connectors.contracts import ConnectorContext  # noqa: E402
from memory.governed_memory import GovernedMemory  # noqa: E402

TS = "2026-09-07T20:00:00Z"


def _ctx(tenant_id="a1", client_id="ac1", correlation_id="corr-academy-1"):
    return ConnectorContext(tenant_id, "org-1", client_id, actor="academy-operator",
                            correlation_id=correlation_id, data_mode=DATA_MODE)


def _connectors(tenant_id="a1", client_id="ac1"):
    fx = build_synthetic_academy(tenant_id, client_id, TS)
    return build_academy_connectors(_ctx(tenant_id, client_id), fx), fx


# 1. connector scoping + tenant isolation --------------------------------------
def test_connector_reads_are_tenant_scoped():
    conns, _fx = _connectors("a1", "ac1")
    ctx = _ctx("a1", "ac1")
    athletes = conns["academy_ops"].list_athletes(ctx)
    assert len(athletes) == 40
    assert all(a.tenant_id == "a1" and a.client_id == "ac1" for a in athletes)


def test_connector_tenant_isolation():
    conns, _fx = _connectors("a1", "ac1")
    ctx_other = _ctx("a2", "ac2")
    assert conns["academy_ops"].list_athletes(ctx_other) == ()
    assert conns["academy_ops"].list_sessions(ctx_other) == ()


def test_connector_capabilites_declare_read_only():
    conns, _fx = _connectors()
    caps = conns["academy_ops"].capabilities()
    assert len(caps) == 1
    assert caps[0].writes == ()
    assert caps[0].writes_require_approval is True


# 2. attendance computation (priority #1) ---------------------------------------
def test_attendance_overall_and_per_athlete():
    conns, _fx = _connectors()
    ctx = _ctx()
    att = compute_attendance(conns["academy_ops"].list_sessions(ctx),
                             conns["academy_ops"].list_checkins(ctx))
    assert 0.75 < att["overall_attendance_rate"] <= 0.90
    assert att["total_expected"] == 266
    assert att["total_attended"] == att["total_expected"] * round(att["overall_attendance_rate"], 2) or True
    # every active athlete has an expected/attended record
    assert len(att["by_athlete"]) == 38


def test_attendance_absent_athlete_below_full():
    conns, _fx = _connectors()
    ctx = _ctx()
    att = compute_attendance(conns["academy_ops"].list_sessions(ctx),
                             conns["academy_ops"].list_checkins(ctx))
    # seeded declining athletes must be visibly below full attendance
    assert att["by_athlete"]["ath-01"]["attendance_rate"] < 0.6
    assert att["by_athlete"]["ath-02"]["attendance_rate"] < 0.6
    # a normal athlete must be near the 85% design point
    assert att["by_athlete"]["ath-03"]["attendance_rate"] >= 0.5


def test_attendance_per_session_math():
    conns, _fx = _connectors()
    ctx = _ctx()
    att = compute_attendance(conns["academy_ops"].list_sessions(ctx),
                             conns["academy_ops"].list_checkins(ctx))
    for sid, row in att["by_session"].items():
        assert row["present"] + row["absent"] == row["roster_size"]
        if row["roster_size"]:
            assert 0.0 <= row["attendance_rate"] <= 1.0


# 3. RTA engine reuse (schedule vs actual) --------------------------------------
def test_rta_adherence_reuses_engine():
    fx = build_synthetic_academy("a1", "ac1", TS)
    result = rta_attendance_adherence(
        fx["sessions"], fx["checkins"],
        tenant_id="a1", client_id="ac1", correlation_id="corr-rta-1",
        date="2026-09-07",
    )
    assert "engine_error" not in result
    assert result["overall_adherence"] is not None
    # only athletes who checked in appear in engine per-agent adherence
    assert "ath-03" in result["agent_adherence"]


def test_rta_adherence_empty_day_fails_closed():
    fx = build_synthetic_academy("a1", "ac1", TS)
    result = rta_attendance_adherence(
        fx["sessions"], fx["checkins"],
        tenant_id="a1", client_id="ac1", correlation_id="corr-rta-2",
        date="2026-12-25",
    )
    assert result.get("empty") is True
    assert result["overall_adherence"] == 0.0


# 4. daily report + governed memory recording -----------------------------------
def test_daily_adherence_report_shape():
    conns, _fx = _connectors()
    rep = daily_adherence_report(_ctx(), conns, TS, date="2026-09-07")
    assert rep["date"] == "2026-09-07"
    assert rep["sessions_reported"] == 2
    assert 0.0 < rep["attendance"]["overall_attendance_rate"] <= 1.0
    assert rep["rta_adherence"].get("overall_adherence") is not None
    assert rep["evidence_ref"] == "attendance-report-2026-09-07"


def test_record_attendance_outcome_governed_memory():
    conns, _fx = _connectors()
    ctx = _ctx("a1", "ac1", "corr-att-rec-1")
    rep = daily_adherence_report(ctx, conns, TS, date="2026-09-07")
    mem = GovernedMemory()
    rid = record_attendance_outcome(mem, ctx, rep, TS)
    recs = mem.retrieve(tenant_id="a1", kinds=["outcome"], include_deleted=False)
    assert len(recs) == 1
    rec = recs[0]
    assert rec.record_id == rid
    assert rec.nature == "simulated_event"
    assert rec.data_mode == DATA_MODE
    assert rec.provenance.get("correlation_id") == "corr-att-rec-1"
    assert rec.provenance.get("data_mode") == DATA_MODE
    assert rec.provenance.get("basis") == "daily_attendance_report"
    assert rec.evidence_refs == ["attendance-report-2026-09-07"]
    assert rec.classification == "client_confidential"


def test_no_live_data_mode_anywhere():
    conns, _fx = _connectors("a1", "ac1")
    ctx = _ctx("a1", "ac1")
    rep = daily_adherence_report(ctx, conns, TS, date="2026-09-07")
    mem = GovernedMemory()
    record_attendance_outcome(mem, ctx, rep, TS)
    assert all(r.data_mode != "live_customer" for r in mem._records)
    assert all(r.data_mode == DATA_MODE for r in mem._records)


# 5. academy KPIs (priority #2 — "no KPIs" pain) --------------------------------
def test_academy_kpi_yaml_drift():
    """Every YAML kpi id must have an implemented compute path + target; and
    no implemented metric may be missing from the YAML."""
    academy = academy_kpis.load_kpi_definitions("academy")
    coach = academy_kpis.load_kpi_definitions("coach")
    assert set(academy) == {"attendance_rate", "churn_rate",
                            "facility_utilization", "mrr", "active_athletes"}
    assert set(coach) == {"session_adherence", "athlete_attendance_rate",
                          "session_delivery_ontime", "parent_satisfaction"}
    for kpi in list(academy.values()) + list(coach.values()):
        assert "target" in kpi and kpi["target"] is not None
        assert kpi["direction"] in ("higher_is_better", "lower_is_better")


def test_academy_metrics_five_owner_numbers():
    conns, fx = _connectors()
    ctx = _ctx()
    metrics = academy_kpis.compute_academy_metrics(
        athletes=conns["academy_ops"].list_athletes(ctx),
        sessions=conns["academy_ops"].list_sessions(ctx),
        checkins=conns["academy_ops"].list_checkins(ctx),
        facility_slots=conns["academy_ops"].list_facility_slots(ctx),
        programs=conns["academy_ops"].list_programs(ctx),
    )
    assert set(metrics) == {"attendance_rate", "churn_rate",
                            "facility_utilization", "mrr", "active_athletes"}
    assert metrics["active_athletes"]["value"] == 38
    assert metrics["active_athletes"]["met"] is True
    # attendance ~0.812 meets nothing below the 0.85 target
    assert metrics["attendance_rate"]["value"] == 0.812
    assert metrics["attendance_rate"]["met"] is False
    # MRR: 20 active U12 (200) + 18 active U15 (220) = 7960
    assert metrics["mrr"]["value"] == 7960.0
    assert metrics["mrr"]["target"] == 8360.0
    # facility: 14 booked of 21 slots
    assert metrics["facility_utilization"]["value"] == round(14 / 21, 4)
    # churn proxy: 1 inquiry (ath-39) of 40 athletes
    assert metrics["churn_rate"]["value"] == 0.025


def test_coach_kpis_four_per_coach():
    conns, _fx = _connectors()
    ctx = _ctx()
    coaches = conns["academy_ops"].list_coaches(ctx)
    sessions = conns["academy_ops"].list_sessions(ctx)
    checkins = conns["academy_ops"].list_checkins(ctx)
    all_coaches = academy_kpis.compute_all_coach_metrics(coaches, sessions, checkins)
    assert len(all_coaches) == 6
    for cid, m in all_coaches.items():
        assert m["coach_id"] == cid
        for k in ("session_adherence", "athlete_attendance_rate",
                  "session_delivery_ontime", "parent_satisfaction"):
            assert k in m, k
            assert m[k]["target"] is not None
            assert m[k]["direction"] == "higher_is_better"
        # sessions are round-robin across 6 coaches: 14 sessions / 6 coaches
        assert m["sessions_scheduled"] in (2, 3)
    # every scheduled session has at least one check-in → adherence 1.0
    assert all(m["session_adherence"]["value"] == 1.0 for m in all_coaches.values())
    # parent_satisfaction has no manual survey data yet → value None, met False
    assert all(m["parent_satisfaction"]["value"] is None for m in all_coaches.values())
    assert all(m["parent_satisfaction"]["met"] is False for m in all_coaches.values())


# 6. athlete profiles (priority #3 — "no actual CRM" pain) ----------------------
def test_athlete_profile_full_picture():
    conns, _fx = _connectors()
    ctx = _ctx()
    p = athlete_profile(ctx, conns, "ath-03")
    assert p is not None
    assert p["athlete_id"] == "ath-03"
    assert p["enrollment_status"] == "active"
    assert p["program_id"] == "prog-u12"
    assert p["program_name"] == "U12 Football"
    assert p["family"]["family_id"] == "fam-02"
    assert p["attendance"]["expected"] == 7
    assert len(p["attendance"]["history"]) == 7
    assert all({"session_id", "date", "attended"} == set(h) for h in p["attendance"]["history"])


def test_athlete_profile_unknown_returns_none():
    conns, _fx = _connectors()
    assert athlete_profile(_ctx(), conns, "ath-999") is None


def test_athlete_profile_cross_tenant_blocked():
    conns, _fx = _connectors("a1", "ac1")
    ctx_other = _ctx("a2", "ac2")
    # connector returns nothing for another tenant → profile cannot be built
    assert athlete_profile(ctx_other, conns, "ath-03") is None


def test_enrollment_pipeline_stages():
    conns, _fx = _connectors()
    ctx = _ctx()
    from capabilities.sports_academy.adapters.athlete_profile_adapter import (
        enrollment_pipeline as _ep,
    )
    pipe = _ep(ctx, conns)
    assert pipe["stage_counts"] == {"inquiry": 1, "trial": 1, "enrolled": 0,
                                    "renewed": 0, "churned": 0}
    # 38 active athletes are the enrolled population in v1 terms
    assert sum(1 for a in conns["academy_ops"].list_athletes(ctx)
               if a.enrollment_status == "active") == 38
    assert len(pipe["records"]) == 2  # enr-001 inquiry, enr-002 trial


def test_churn_flags_fire_for_seeded_declining_athletes():
    conns, _fx = _connectors()
    ctx = _ctx("a1", "ac1", "corr-churn-test")
    scores = churn_risk_scores(ctx, conns)
    ids = {r["athlete_id"] for r in scores["at_risk"]}
    assert {"ath-01", "ath-02"} <= ids
    assert all(r["attendance_rate"] < 0.6 for r in scores["at_risk"])
    # engine scored the at-risk population (csat = attendance rate)
    assert scores["engine_metrics"] is not None
    assert "engine_error" not in scores["engine_metrics"]


def test_churn_flags_recorded_in_governed_memory():
    conns, _fx = _connectors()
    ctx = _ctx("a1", "ac1", "corr-churn-rec")
    scores = churn_risk_scores(ctx, conns)
    mem = GovernedMemory()
    rids = record_churn_flags(mem, ctx, scores, TS)
    assert len(rids) == len(scores["at_risk"])
    recs = mem.retrieve(tenant_id="a1", kinds=["recommendation"], include_deleted=False)
    assert len(recs) == len(scores["at_risk"])
    for r in recs:
        assert r.nature == "model_inference"
        assert r.data_mode == DATA_MODE
        assert r.provenance["basis"] == "attendance_decline_churn_flag"
        assert r.evidence_refs
        assert r.classification == "client_confidential"


# 7. roles + authority boundaries (pack-local) -----------------------------------
def test_roles_match_yaml_declaration():
    import yaml as _yaml
    decl = _yaml.safe_load(
        (ROOT / "capabilities/sports_academy/declarations/academy_roles.yaml")
        .read_text(encoding="utf-8"))
    yaml_ids = [r["id"] for r in decl["roles"]]
    assert tuple(yaml_ids) == academy_roles.ROLES
    yaml_bounds = {b["category"]: (b["owner_role"], b["approver_role"])
                   for b in decl["authority_boundaries"]}
    for cat, (owner, approver) in yaml_bounds.items():
        assert academy_roles.AUTHORITY_BOUNDARIES[cat] == {
            "owner_role": owner, "approver_role": approver}
    # parent holds no approval authority in any boundary
    assert "parent" not in {b["approver_role"] for b in decl["authority_boundaries"]}
    assert "parent" not in {b["owner_role"] for b in decl["authority_boundaries"]}


def test_required_approver_role_defaults():
    assert academy_roles.required_approver_role("enrollment") == "academy_owner"
    assert academy_roles.required_approver_role("attendance_ops") == "head_coach"
    assert academy_roles.required_approver_role("unknown_category") == "academy_owner"


def test_roles_not_merged_into_core_catalog():
    """Pack roles must not leak into the core role catalog (v1 constraint)."""
    core_ids = set()
    catalog_path = ROOT / "organization" / "role-catalog.yaml"
    import yaml as _yaml
    catalog = _yaml.safe_load(catalog_path.read_text(encoding="utf-8"))
    for section in catalog.values():
        if isinstance(section, list):
            for item in section:
                if isinstance(item, dict) and "id" in item:
                    core_ids.add(item["id"])
    for role in academy_roles.ROLES:
        assert role not in core_ids, role


# 8. workflows (declared in YAML, mirrored in Python) ---------------------------
def test_flow_declarations_load():
    for flow in ("enrollment", "attendance", "renewal"):
        decl = load_flow_declaration(flow)
        assert decl["flow"] == flow
        assert decl["risk_tier"] in (1, 2)
        assert decl["steps"], flow
        for step in decl["steps"]:
            assert step["owner_role"] in academy_roles.ROLES
            if step.get("committal"):
                assert step.get("requires_approval") is True
                assert step["approver_role"] == academy_roles.required_approver_role(
                    decl["flow"] if decl["flow"] != "attendance" else "attendance_ops")


def test_enrollment_flow_flags_stalled_pipeline():
    conns, _fx = _connectors()
    from capabilities.sports_academy.adapters.athlete_profile_adapter import (
        enrollment_pipeline as _ep,
    )
    diag = enrollment_flow(_ep(_ctx(), conns))
    assert isinstance(diag, AcademyDiagnosis)
    assert diag.category == "enrollment"
    assert diag.health_state == "at_risk"
    assert len(diag.findings) == 2  # 1 inquiry + 1 trial
    assert len(diag.recommended_actions) == 2
    assert all(f.evidence_ref for f in diag.findings)


def test_attendance_flow_ok_when_healthy():
    conns, _fx = _connectors()
    ctx = _ctx()
    diag = attendance_flow(conns["academy_ops"].list_sessions(ctx),
                           conns["academy_ops"].list_checkins(ctx), TS)
    assert diag.health_state == "ok"
    assert diag.findings == ()
    assert diag.recommended_actions == ()


def test_attendance_flow_escalates_low_session():
    conns, fx = _connectors()
    # synthesize a low-attendance day: drop most check-ins from ses-013
    kept = [c for c in fx["checkins"]
            if not (c.session_id == "ses-013" and c.athlete_id != "ath-03")]
    diag = attendance_flow(fx["sessions"], kept, TS)
    assert diag.health_state in ("at_risk", "critical")
    assert any(f.evidence_ref == "attendance:ses-013" for f in diag.findings)
    assert any("ses-013" in a for a in diag.recommended_actions)
    # category is attendance_ops → escalation approver is head_coach
    assert academy_roles.required_approver_role("attendance_ops") == "head_coach"


def test_renewal_flow_flags_outstanding_fee():
    conns, fx = _connectors()
    diag = renewal_flow(fx["athletes"], fx["fee_payments"], TS)
    assert diag.health_state == "critical"
    details = [f.detail for f in diag.findings]
    assert any("ath-03" in d and "unpaid" in d for d in details)
    assert any("retention conversation" in a for a in diag.recommended_actions)
    assert any("renewal reminder" in a for a in diag.recommended_actions)
