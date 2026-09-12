"""Owner dashboard (v1) — the 5 most important numbers, one screen.

Pure compute + thin Streamlit render. The 5 numbers: active athletes, MRR,
7-day attendance rate, at-risk athletes (churn flags), facility utilization.
Plus the awaiting-approval count for the governance rail.
"""
from __future__ import annotations

from typing import Any, Dict

from connectors.contracts import ConnectorContext

from ..adapters.athlete_profile_adapter import churn_risk_signals
from ..adapters.attendance_adapter import compute_attendance
from .. import kpis as academy_kpis

DATA_MODE = "simulated_realistic"


def compute_owner_dashboard(
    ctx: ConnectorContext,
    connectors: Dict[str, Any],
    as_of: str,
) -> Dict[str, Any]:
    """The 5 owner numbers + churn-risk names + KPI target metadata."""
    conn = connectors["academy_ops"]
    athletes = conn.list_athletes(ctx)
    sessions = conn.list_sessions(ctx)
    checkins = conn.list_checkins(ctx)
    slots = conn.list_facility_slots(ctx)
    programs = conn.list_programs(ctx)

    metrics = academy_kpis.compute_academy_metrics(
        athletes=athletes,
        sessions=sessions,
        checkins=checkins,
        facility_slots=slots,
        programs=programs,
    )
    attendance = compute_attendance(sessions, checkins)
    at_risk = list(churn_risk_signals(ctx, connectors))
    return {
        "as_of": as_of,
        "data_mode": DATA_MODE,
        "kpis": metrics,
        "attendance_7d": attendance["overall_attendance_rate"],
        "at_risk_athletes": at_risk,
        "sessions_total": len(sessions),
        "enrollment_pipeline": {
            "inquiry": sum(1 for a in athletes if a.enrollment_status == "inquiry"),
            "trial": sum(1 for a in athletes if a.enrollment_status == "trial"),
        },
    }


def render_owner_dashboard(
    st, ctx: ConnectorContext, connectors: Dict[str, Any], as_of: str
) -> None:
    """Streamlit wiring — thin; logic lives in compute_owner_dashboard."""
    board = compute_owner_dashboard(ctx, connectors, as_of)
    st.markdown(
        f"<span style='background:#3B3B4F;color:#FFD166;padding:2px 10px;"
        f"border-radius:4px;font-size:0.8rem;font-weight:700;'>"
        f"DATA MODE: {board['data_mode']} — synthetic, not live</span>",
        unsafe_allow_html=True,
    )
    k = board["kpis"]
    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric(
        "Active athletes",
        k["active_athletes"]["value"],
        delta=f"target {k['active_athletes']['target']}",
    )
    col2.metric("MRR (USD)", f"{k['mrr']['value']:,.0f}", delta=f"target {k['mrr']['target']:,.0f}")
    col3.metric(
        "Attendance (7d)",
        f"{board['attendance_7d']:.0%}",
        delta=f"target {k['attendance_rate']['target']:.0%}",
        delta_color="normal" if k["attendance_rate"]["met"] else "inverse",
    )
    col4.metric(
        "At-risk athletes",
        len(board["at_risk_athletes"]),
        delta=f"churn target {k['churn_rate']['target']:.0%}",
    )
    col5.metric(
        "Facility utilization",
        f"{k['facility_utilization']['value']:.0%}",
        delta=f"target {k['facility_utilization']['target']:.0%}",
    )
    st.divider()
    if board["at_risk_athletes"]:
        st.markdown("**At-risk athletes (attendance below 60%)**")
        st.dataframe(
            [
                {
                    "athlete_id": r["athlete_id"],
                    "attendance_rate": f"{r['attendance_rate']:.0%}",
                    "attended": f"{r['attended']}/{r['expected']}",
                }
                for r in board["at_risk_athletes"]
            ],
            hide_index=True,
        )
    else:
        st.success("No at-risk athletes detected.")
    pipe = board["enrollment_pipeline"]
    st.caption(
        f"Enrollment pipeline: {pipe['inquiry']} inquiry, {pipe['trial']} trial · "
        f"{board['sessions_total']} sessions in window · as of {board['as_of']}"
    )
