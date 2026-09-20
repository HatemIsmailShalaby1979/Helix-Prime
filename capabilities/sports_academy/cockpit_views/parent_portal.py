"""Parent portal (v1) — read-only schedule, attendance, billing for own children.

Web-only (no mobile app — explicit v1 non-goal). The parent role holds no
approval authority; this view exposes exactly what a parent may see: their
own family's athletes' schedule, attendance, and fee status. Nothing else.
"""
from __future__ import annotations

from typing import Any, Dict

from connectors.contracts import ConnectorContext
from contracts.vocabulary import CONNECTOR_SIMULATED_REALISTIC

from ..adapters.attendance_adapter import compute_attendance

DATA_MODE = CONNECTOR_SIMULATED_REALISTIC


def compute_parent_view(
    ctx: ConnectorContext,
    connectors: Dict[str, Any],
    as_of: str,
    family_id: str,
) -> Dict[str, Any]:
    """One family's read-only view: athletes, schedule, attendance, fees."""
    conn = connectors["academy_ops"]
    families = [f for f in conn.list_families(ctx) if f.family_id == family_id]
    if not families:
        return {"error": "unknown_family", "family_id": family_id}
    family = families[0]
    athletes = [a for a in conn.list_athletes(ctx) if a.family_id == family_id]
    athlete_ids = {a.athlete_id for a in athletes}
    sessions = [s for s in conn.list_sessions(ctx) if any(aid in s.roster for aid in athlete_ids)]
    checkins = [c for c in conn.list_checkins(ctx) if c.athlete_id in athlete_ids]
    attendance = compute_attendance(sessions, checkins)
    fees = [p for p in conn.list_fee_payments(ctx) if p.family_id == family_id]
    return {
        "as_of": as_of,
        "data_mode": DATA_MODE,
        "family": {
            "family_id": family.family_id,
            "primary_contact_name": family.primary_contact_name,
        },
        "athletes": [
            {
                "athlete_id": a.athlete_id,
                "name": a.name,
                "program_id": a.program_id,
                "enrollment_status": a.enrollment_status,
            }
            for a in athletes
        ],
        "schedule": [
            {
                "session_id": s.session_id,
                "date": s.date,
                "start": s.start,
                "end": s.end,
                "program_id": s.program_id,
            }
            for s in sorted(sessions, key=lambda s: (s.date, s.start))
        ],
        "attendance_by_athlete": {
            aid: {
                "expected": v["expected"],
                "attended": v["attended"],
                "rate": v["attendance_rate"],
            }
            for aid, v in attendance["by_athlete"].items()
            if aid in athlete_ids
        },
        "fees": [
            {
                "payment_id": p.payment_id,
                "athlete_id": p.athlete_id,
                "amount": p.amount,
                "due_date": p.due_date,
                "status": "paid" if p.paid_at else "outstanding",
            }
            for p in fees
        ],
    }


def render_parent_view(
    st, ctx: ConnectorContext, connectors: Dict[str, Any], as_of: str, family_id: str
) -> None:
    """Streamlit wiring — thin; logic lives in compute_parent_view."""
    view = compute_parent_view(ctx, connectors, as_of, family_id)
    if "error" in view:
        st.error(f"Unknown family {view['family_id']}")
        return
    st.markdown(
        f"<span style='background:#3B3B4F;color:#FFD166;padding:2px 10px;"
        f"border-radius:4px;font-size:0.8rem;font-weight:700;'>"
        f"DATA MODE: {view['data_mode']} — synthetic, not live</span>",
        unsafe_allow_html=True,
    )
    st.subheader(f"Family portal — {view['family']['primary_contact_name']}")
    st.markdown("**Athletes**")
    st.dataframe(view["athletes"], hide_index=True)
    if view["athletes"]:
        st.markdown("**Attendance**")
        st.dataframe(
            [
                {
                    "athlete_id": aid,
                    "attended": f"{v['attended']}/{v['expected']}",
                    "rate": f"{v['rate']:.0%}",
                }
                for aid, v in view["attendance_by_athlete"].items()
            ],
            hide_index=True,
        )
        st.markdown("**Upcoming/past sessions**")
        st.dataframe(view["schedule"], hide_index=True)
    st.markdown("**Billing (manual records)**")
    if view["fees"]:
        st.dataframe(view["fees"], hide_index=True)
    else:
        st.info("No fee records for this family.")
