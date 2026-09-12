"""Coach dashboard (v1) — today's sessions, athlete progress, own KPIs.

Pure compute + thin Streamlit render. KPI values render against the targets
declared in declarations/coach_kpis.yaml.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from connectors.contracts import ConnectorContext

from .. import kpis as academy_kpis
from ..adapters.attendance_adapter import compute_attendance

DATA_MODE = "simulated_realistic"


def compute_coach_dashboard(
    ctx: ConnectorContext,
    connectors: Dict[str, Any],
    as_of: str,
    coach_id: str,
    date: Optional[str] = None,
) -> Dict[str, Any]:
    """Today's sessions + roster attendance + the 4 coach KPIs."""
    conn = connectors["academy_ops"]
    coaches = [c for c in conn.list_coaches(ctx) if c.coach_id == coach_id]
    if not coaches:
        return {"error": "unknown_coach", "coach_id": coach_id}
    coach = coaches[0]
    sessions = conn.list_sessions(ctx)
    checkins = conn.list_checkins(ctx)

    today_sessions = [
        s for s in sessions if s.coach_id == coach_id and (date is None or s.date == date)
    ]
    day_ids = {s.session_id for s in today_sessions}
    today_checkins = [c for c in checkins if c.session_id in day_ids]
    today_attendance = compute_attendance(today_sessions, today_checkins)

    kpis = academy_kpis.compute_coach_metrics(coach, sessions, checkins)
    return {
        "as_of": as_of,
        "date": date or as_of[:10],
        "data_mode": DATA_MODE,
        "coach": {"coach_id": coach.coach_id, "name": coach.name},
        "today_sessions": [
            {
                "session_id": s.session_id,
                "date": s.date,
                "start": s.start,
                "end": s.end,
                "program_id": s.program_id,
                "roster_size": len(s.roster),
            }
            for s in sorted(today_sessions, key=lambda s: (s.date, s.start))
        ],
        "today_attendance": today_attendance["by_session"],
        "kpis": kpis,
    }


def render_coach_dashboard(
    st,
    ctx: ConnectorContext,
    connectors: Dict[str, Any],
    as_of: str,
    coach_id: str,
    date: Optional[str] = None,
) -> None:
    """Streamlit wiring — thin; logic lives in compute_coach_dashboard."""
    board = compute_coach_dashboard(ctx, connectors, as_of, coach_id, date)
    if "error" in board:
        st.error(f"Unknown coach {board['coach_id']}")
        return
    st.markdown(
        f"<span style='background:#3B3B4F;color:#FFD166;padding:2px 10px;"
        f"border-radius:4px;font-size:0.8rem;font-weight:700;'>"
        f"DATA MODE: {board['data_mode']} — synthetic, not live</span>",
        unsafe_allow_html=True,
    )
    st.subheader(f"{board['coach']['name']} — {board['date']}")
    if board["today_sessions"]:
        st.markdown("**Today's sessions**")
        st.dataframe(board["today_sessions"], hide_index=True)
        for sid, row in board["today_attendance"].items():
            st.progress(
                row["attendance_rate"],
                text=f"{sid}: {row['present']}/{row['roster_size']} "
                f"({row['attendance_rate']:.0%})",
            )
    else:
        st.info("No sessions scheduled today.")
    st.divider()
    st.markdown("**Your KPIs (v1: progression tracking requires curriculum definition)**")
    k = board["kpis"]
    col1, col2, col3, col4 = st.columns(4)
    for col, key, fmt in (
        (col1, "session_adherence", "{:.0%}"),
        (col2, "athlete_attendance_rate", "{:.0%}"),
        (col3, "session_delivery_ontime", "{:.0%}"),
        (col4, "parent_satisfaction", "{:.0%}"),
    ):
        entry = k[key]
        value = "—" if entry["value"] is None else fmt.format(entry["value"])
        met = "✓" if entry["met"] else "○"
        col.metric(
            f"{met} {key.replace('_', ' ').title()}",
            value,
            delta=f"target {entry['target']:.0%}"
            if isinstance(entry["target"], float)
            else f"target {entry['target']}",
        )
