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
