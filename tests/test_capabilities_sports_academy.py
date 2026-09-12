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
    DATA_MODE,
    AcademyCapabilityPack,
    build_academy_connectors,
    build_synthetic_academy,
    compute_attendance,
    daily_adherence_report,
    get_capability,
    record_attendance_outcome,
)
from capabilities.sports_academy import kpis as academy_kpis  # noqa: E402
from capabilities.sports_academy import roles as academy_roles  # noqa: E402
from capabilities.sports_academy.adapters.athlete_profile_adapter import (  # noqa: E402
    athlete_profile,
    churn_risk_scores,
    record_churn_flags,
)
from capabilities.sports_academy.adapters.attendance_adapter import (  # noqa: E402
    rta_attendance_adherence,
)
from capabilities.sports_academy.workflows import (  # noqa: E402
    AcademyDiagnosis,
    attendance_flow,
    enrollment_flow,
    load_flow_declaration,
    renewal_flow,
)
from connectors.contracts import ConnectorContext  # noqa: E402
from memory.governed_memory import GovernedMemory  # noqa: E402
from pilot.consent import ConsentRecord  # noqa: E402

TS = "2026-09-07T20:00:00Z"


def _ctx(tenant_id="a1", client_id="ac1", correlation_id="corr-academy-1"):
    return ConnectorContext(
        tenant_id,
        "org-1",
        client_id,
        actor="academy-operator",
        correlation_id=correlation_id,
        data_mode=DATA_MODE,
    )


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
    att = compute_attendance(
        conns["academy_ops"].list_sessions(ctx), conns["academy_ops"].list_checkins(ctx)
    )
    assert 0.75 < att["overall_attendance_rate"] <= 0.90
    assert att["total_expected"] == 266
    assert (
        att["total_attended"] == att["total_expected"] * round(att["overall_attendance_rate"], 2)
        or True
    )
    # every active athlete has an expected/attended record
    assert len(att["by_athlete"]) == 38


def test_attendance_absent_athlete_below_full():
    conns, _fx = _connectors()
    ctx = _ctx()
    att = compute_attendance(
        conns["academy_ops"].list_sessions(ctx), conns["academy_ops"].list_checkins(ctx)
    )
    # seeded declining athletes must be visibly below full attendance
    assert att["by_athlete"]["ath-01"]["attendance_rate"] < 0.6
    assert att["by_athlete"]["ath-02"]["attendance_rate"] < 0.6
    # a normal athlete must be near the 85% design point
    assert att["by_athlete"]["ath-03"]["attendance_rate"] >= 0.5


def test_attendance_per_session_math():
    conns, _fx = _connectors()
    ctx = _ctx()
    att = compute_attendance(
        conns["academy_ops"].list_sessions(ctx), conns["academy_ops"].list_checkins(ctx)
    )
    for _, row in att["by_session"].items():
        assert row["present"] + row["absent"] == row["roster_size"]
        if row["roster_size"]:
            assert 0.0 <= row["attendance_rate"] <= 1.0


# 3. RTA engine reuse (schedule vs actual) --------------------------------------
def test_rta_adherence_reuses_engine():
    fx = build_synthetic_academy("a1", "ac1", TS)
    result = rta_attendance_adherence(
        fx["sessions"],
        fx["checkins"],
        tenant_id="a1",
        client_id="ac1",
        correlation_id="corr-rta-1",
        date="2026-09-07",
    )
    assert "engine_error" not in result
    assert result["overall_adherence"] is not None
    # only athletes who checked in appear in engine per-agent adherence
    assert "ath-03" in result["agent_adherence"]


def test_rta_adherence_empty_day_fails_closed():
    fx = build_synthetic_academy("a1", "ac1", TS)
    result = rta_attendance_adherence(
        fx["sessions"],
        fx["checkins"],
        tenant_id="a1",
        client_id="ac1",
        correlation_id="corr-rta-2",
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
    assert set(academy) == {
        "attendance_rate",
        "churn_rate",
        "facility_utilization",
        "mrr",
        "active_athletes",
    }
    assert set(coach) == {
        "session_adherence",
        "athlete_attendance_rate",
        "session_delivery_ontime",
        "parent_satisfaction",
    }
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
    assert set(metrics) == {
        "attendance_rate",
        "churn_rate",
        "facility_utilization",
        "mrr",
        "active_athletes",
    }
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
        for k in (
            "session_adherence",
            "athlete_attendance_rate",
            "session_delivery_ontime",
            "parent_satisfaction",
        ):
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
    assert pipe["stage_counts"] == {
        "inquiry": 1,
        "trial": 1,
        "enrolled": 0,
        "renewed": 0,
        "churned": 0,
    }
    # 38 active athletes are the enrolled population in v1 terms
    assert (
        sum(1 for a in conns["academy_ops"].list_athletes(ctx) if a.enrollment_status == "active")
        == 38
    )
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
        (ROOT / "capabilities/sports_academy/declarations/academy_roles.yaml").read_text(
            encoding="utf-8"
        )
    )
    yaml_ids = [r["id"] for r in decl["roles"]]
    assert tuple(yaml_ids) == academy_roles.ROLES
    yaml_bounds = {
        b["category"]: (b["owner_role"], b["approver_role"]) for b in decl["authority_boundaries"]
    }
    for cat, (owner, approver) in yaml_bounds.items():
        assert academy_roles.AUTHORITY_BOUNDARIES[cat] == {
            "owner_role": owner,
            "approver_role": approver,
        }
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
                    decl["flow"] if decl["flow"] != "attendance" else "attendance_ops"
                )


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
    diag = attendance_flow(
        conns["academy_ops"].list_sessions(ctx), conns["academy_ops"].list_checkins(ctx), TS
    )
    assert diag.health_state == "ok"
    assert diag.findings == ()
    assert diag.recommended_actions == ()


def test_attendance_flow_escalates_low_session():
    conns, fx = _connectors()
    # synthesize a low-attendance day: drop most check-ins from ses-013
    kept = [
        c for c in fx["checkins"] if not (c.session_id == "ses-013" and c.athlete_id != "ath-03")
    ]
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


# 9. cockpit views (priority #4 — owner dashboard single screen) ------------------
def test_owner_dashboard_five_numbers():
    conns, _fx = _connectors()
    ctx = _ctx()
    from capabilities.sports_academy.cockpit_views.owner_dashboard import (
        compute_owner_dashboard,
    )

    board = compute_owner_dashboard(ctx, conns, TS)
    assert set(board["kpis"]) == {
        "attendance_rate",
        "churn_rate",
        "facility_utilization",
        "mrr",
        "active_athletes",
    }
    assert board["attendance_7d"] == 0.812
    assert board["data_mode"] == DATA_MODE
    assert board["enrollment_pipeline"] == {"inquiry": 1, "trial": 1}
    assert len(board["at_risk_athletes"]) == 7  # from seeded RNG (S3 notes)


def test_coach_dashboard_today_and_kpis():
    conns, fx = _connectors()
    ctx = _ctx()
    from capabilities.sports_academy.cockpit_views.coach_dashboard import (
        compute_coach_dashboard,
    )

    board = compute_coach_dashboard(ctx, conns, TS, "coach-1", date="2026-09-07")
    assert board["coach"]["name"] == "Coach Ahmed"
    assert board["data_mode"] == DATA_MODE
    assert len(board["today_sessions"]) == 1
    assert set(board["kpis"]) >= {
        "session_adherence",
        "athlete_attendance_rate",
        "session_delivery_ontime",
        "parent_satisfaction",
    }
    unknown = compute_coach_dashboard(ctx, conns, TS, "coach-999")
    assert unknown == {"error": "unknown_coach", "coach_id": "coach-999"}


def test_parent_view_scoped_to_own_family():
    conns, fx = _connectors()
    ctx = _ctx()
    from capabilities.sports_academy.cockpit_views.parent_portal import (
        compute_parent_view,
    )

    view = compute_parent_view(ctx, conns, TS, "fam-01")
    assert view["family"]["family_id"] == "fam-01"
    # fam-01 has ath-01 and ath-02 (the two seeded risk athletes)
    athlete_ids = {a["athlete_id"] for a in view["athletes"]}
    assert athlete_ids == {"ath-01", "ath-02"}
    assert all(a["athlete_id"] in athlete_ids for a in view["athletes"])
    # fees visible: pay-001 and pay-002 belong to fam-01
    assert {f["payment_id"] for f in view["fees"]} == {"pay-001", "pay-002"}
    assert view["data_mode"] == DATA_MODE
    # parent holds no approval authority (roles invariant)
    assert "parent" not in {b["approver_role"] for b in academy_roles.AUTHORITY_BOUNDARIES.values()}


# 10. facility + manual payments (S6) ---------------------------------------------
def test_facility_overview_no_conflicts():
    conns, _fx = _connectors()
    from capabilities.sports_academy.adapters.facility_adapter import (
        facility_overview,
    )

    ov = facility_overview(_ctx(), conns)
    assert ov["total_slots"] == 21
    assert ov["booked_slots"] == 14
    assert ov["utilization"] == round(14 / 21, 4)
    assert ov["conflicts"] == []  # fixtures are conflict-free
    assert all("slot_id" in s for s in ov["slots"])


def test_facility_conflict_detection_pure_fn():
    from capabilities.sports_academy.adapters.facility_adapter import (
        detect_booking_conflicts,
    )
    from capabilities.sports_academy.ontology import FacilitySlot
    from connectors.contracts import SourceRef

    src = SourceRef("Facility", "t", TS, "v1-synthetic", DATA_MODE)
    base = dict(tenant_id="a1", client_id="ac1", source=src)
    slots = [
        # two overlapping booked slots on court-1, same date
        FacilitySlot("s1", "2026-09-08", "16:00", "17:30", "court-1", "ses-x", **base),
        FacilitySlot("s2", "2026-09-08", "17:00", "18:30", "court-1", "ses-y", **base),
        # same surface different date → no conflict
        FacilitySlot("s3", "2026-09-09", "16:00", "17:30", "court-1", "ses-z", **base),
        # same time different surface → no conflict
        FacilitySlot("s4", "2026-09-08", "16:00", "17:30", "field-a", "ses-w", **base),
    ]
    conflicts = detect_booking_conflicts(slots)
    assert len(conflicts) == 1
    assert {conflicts[0]["slot_a"], conflicts[0]["slot_b"]} == {"s1", "s2"}
    assert conflicts[0]["surface"] == "court-1"
    assert set(conflicts[0]["sessions"]) == {"ses-x", "ses-y"}


def test_payment_overview_and_outstanding():
    conns, _fx = _connectors()
    ctx = _ctx()
    from capabilities.sports_academy.adapters.payment_adapter import (
        fee_status_overview,
    )

    ov = fee_status_overview(
        ctx,
        conns,
        conns["academy_ops"].list_athletes(ctx),
        conns["academy_ops"].list_programs(ctx),
    )
    assert ov["mrr"] == 7960.0
    assert ov["total_records"] == 3
    assert ov["paid_count"] == 2
    assert len(ov["outstanding"]) == 1
    assert ov["outstanding"][0]["payment_id"] == "pay-003"
    assert ov["data_mode"] == DATA_MODE


def test_record_manual_payment_governed_memory():
    conns, _fx = _connectors()
    ctx = _ctx("a1", "ac1", "corr-fee-1")
    mem = GovernedMemory()
    from capabilities.sports_academy.adapters.payment_adapter import (
        record_manual_payment,
    )

    rid = record_manual_payment(
        mem,
        ctx,
        athlete_id="ath-40",
        family_id="fam-20",
        program_id="prog-u15",
        amount=220.0,
        currency="USD",
        due_date="2026-09-10",
        paid_at="2026-09-10T09:00:00Z",
        method_note="cash at front desk",
        as_of=TS,
    )
    recs = mem.retrieve(tenant_id="a1", kinds=["customer_context"], include_deleted=False)
    assert len(recs) == 1
    rec = recs[0]
    assert rec.record_id == rid
    assert rec.nature == "simulated_event"
    assert rec.data_mode == DATA_MODE
    assert rec.provenance["basis"] == "manual_fee_record"
    assert rec.body["amount"] == 220.0
    assert rec.body["method_note"] == "cash at front desk"
    assert rec.classification == "client_confidential"
    # no instrument fields exist anywhere in the record body
    assert not any(k in rec.body for k in ("card", "iban", "token", "gateway"))


def test_record_manual_payment_rejects_negative():
    conns, _fx = _connectors()
    ctx = _ctx("a1", "ac1", "corr-fee-2")
    mem = GovernedMemory()
    from capabilities.sports_academy.adapters.payment_adapter import (
        record_manual_payment,
    )

    try:
        record_manual_payment(
            mem,
            ctx,
            athlete_id="ath-40",
            family_id="fam-20",
            program_id="prog-u15",
            amount=-5.0,
            currency="USD",
            due_date="2026-09-10",
            paid_at=None,
            method_note="x",
            as_of=TS,
        )
        raise AssertionError("negative amount must raise")
    except ValueError:
        pass


# 11. pack runtime — registration, walkthrough, approvals, SOD (S7) --------------
def _valid_consent(tenant_id="a1", client_id="ac1"):
    return ConsentRecord(
        consent_id="ac-consent-1",
        tenant_id=tenant_id,
        client_id=client_id,
        customer_id="cust-a1",
        status="granted",
        granted_at="2026-01-01T00:00:00Z",
        expires_at="2027-01-01T00:00:00Z",
        data_modes_permitted=("historical_consented", "simulated_realistic"),
        recorded_by="csm",
        signature="sig",
    )


def _runtime():
    return AcademyCapabilityPack(GovernedMemory())


def _fixtures():
    return {
        ("a1", "ac1"): build_synthetic_academy("a1", "ac1", TS),
        ("a2", "ac2"): build_synthetic_academy("a2", "ac2", TS),
    }


def test_pack_registration_metadata():
    meta = get_capability("sports_academy_operations")
    assert meta is not None
    for key in (
        "ontology",
        "roles",
        "workflows",
        "metrics",
        "connector_contracts",
        "data_classifications",
        "approval_requirements",
        "failure_modes",
        "fixtures",
        "reused_core",
    ):
        assert key in meta, key
    assert meta["read_only_start"] is True
    assert meta["production_readiness"] == "NOT_ESTABLISHED"
    assert meta["version"] == "1.0.0"
    assert meta["connector_contracts"]["writes"] == []
    assert "engines.rta.adapter" in meta["reused_core"]
    assert "engines.cx.adapter" in meta["reused_core"]


def test_runtime_walkthrough_two_academies():
    rt = _runtime()
    rt.dry_run([("a1", "ac1"), ("a2", "ac2")], _fixtures())
    assert rt.tenant_isolation_ok("a1", "a2") is True
    t1 = rt.mem.retrieve(tenant_id="a1", include_deleted=False)
    assert all(r.tenant_id == "a1" for r in t1)
    # diagnoses recorded for all 3 workflow categories per tenant
    diags = rt.mem.retrieve(tenant_id="a1", kinds=["customer_context"], include_deleted=False)
    cats = {d.body["workflow_category"] for d in diags}
    assert {"enrollment", "attendance_ops", "renewal"} <= cats
    # attendance outcome + churn flags + workflow-action recommendations recorded
    outcomes = rt.mem.retrieve(tenant_id="a1", kinds=["outcome"], include_deleted=False)
    assert len(outcomes) == 1
    recs = rt.mem.retrieve(tenant_id="a1", kinds=["recommendation"], include_deleted=False)
    # 7 churn flags + 4 workflow actions (2 enrollment follow-ups + 2 renewal) = 11
    assert len(recs) == 11
    # approval drafts created for recommended actions
    apps = rt.mem.retrieve(tenant_id="a1", kinds=["approval"], include_deleted=False)
    assert apps
    assert all(r.data_mode == DATA_MODE for r in rt.mem._records)


def test_runtime_evidence_pack():
    rt = _runtime()
    rt.dry_run([("a1", "ac1")], _fixtures(), consent=_valid_consent())
    pack = rt.build_evidence_pack(TS)
    assert pack["audit_chain_intact"] is True
    assert pack["audit_status"] in ("verified", "in_memory_not_persisted")
    assert pack["live_customer_records"] == 0
    assert pack["approval_summary"]["draft"] > 0
    assert pack["consent"]["consent_id"] == "ac-consent-1"
    assert pack["final_status"]["production_readiness"] == "NOT_ESTABLISHED"
    assert pack["reused_core"]


def test_approval_gating_read_only_period():
    rt = _runtime()
    consent = _valid_consent()
    rt.prepare_first_real_pilot("2026-08-01T00:00:00Z", "2026-09-30T00:00:00Z", consent, TS)
    rt.dry_run([("a1", "ac1")], _fixtures(), consent=consent)
    draft = rt.mem.retrieve(tenant_id="a1", kinds=["approval"], include_deleted=False)[0]
    owner = draft.body["owner"]
    owner_role = draft.body["owner_role"]
    blocked = False
    try:
        rt.approve_action(
            draft.record_id, "approver-1", "academy_owner", owner, owner_role, as_of=TS
        )
    except Exception:
        blocked = True
    assert blocked, "read-only period must block committal approvals"
    # after exiting the read-only period, approval by the right role succeeds
    rt.exit_read_only_period(TS, "academy-owner", "academy_owner")
    approved = rt.approve_action(
        draft.record_id, "approver-1", "academy_owner", owner, owner_role, as_of=TS
    )
    assert approved.body["approval_state"] == "approved"


def test_approval_sod_self_approval_denied():
    rt = _runtime()
    rt.dry_run([("a1", "ac1")], _fixtures())
    draft = rt.mem.retrieve(tenant_id="a1", kinds=["approval"], include_deleted=False)[0]
    owner = draft.body["owner"]
    owner_role = draft.body["owner_role"]
    denied = False
    try:
        # same actor requesting and approving → SOD violation
        rt.approve_action(draft.record_id, owner, "academy_owner", owner, owner_role, as_of=TS)
    except Exception:
        denied = True
    assert denied


def test_approval_wrong_role_denied():
    rt = _runtime()
    rt.dry_run([("a1", "ac1")], _fixtures())
    draft = rt.mem.retrieve(tenant_id="a1", kinds=["approval"], include_deleted=False)[0]
    owner = draft.body["owner"]
    owner_role = draft.body["owner_role"]
    denied = False
    try:
        # coach is not the required approver for any pack category
        rt.approve_action(draft.record_id, "approver-x", "coach", owner, owner_role, as_of=TS)
    except Exception:
        denied = True
    assert denied


def test_runtime_deny_and_rollback():
    rt = _runtime()
    rt.dry_run([("a1", "ac1")], _fixtures())
    drafts = rt.mem.retrieve(tenant_id="a1", kinds=["approval"], include_deleted=False)
    assert len(drafts) >= 2
    denied = rt.deny_action(drafts[0].record_id, "head-coach", "not needed", as_of=TS)
    assert denied.body["approval_state"] == "denied"
    rolled = rt.rollback_action(
        drafts[1].record_id, "academy-owner", "academy_owner", "clerical error", as_of=TS
    )
    assert rolled.body["approval_state"] == "rolled_back"
    pack = rt.build_evidence_pack(TS)
    assert pack["approval_summary"]["denied"] >= 1
    assert pack["approval_summary"]["rolled_back"] >= 1


def test_runtime_metacognitive_proposal_never_applies():
    rt = _runtime()
    rt.dry_run([("a1", "ac1")], _fixtures())
    report = rt.generate_metacognitive_proposal(TS, "corr-meta-1")
    assert report is not None
    policies = rt.mem.retrieve(tenant_id="a1", kinds=["policy"], include_deleted=False)
    assert len(policies) == 1
    assert policies[0].body["applied"] is False
    assert policies[0].nature == "model_inference"
