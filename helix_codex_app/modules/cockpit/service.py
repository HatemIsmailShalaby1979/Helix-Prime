"""Read-only cockpit views for managers and owners.

Every method re-checks cockpit.view before it calls the bridge. That is the
second of three gates: the router dependency, this check, and the policy bridge
inside the cockpit bridge itself. A screen that merely hides a link is not a
gate, so all three are real.

Nothing here writes. The cockpit shows state and changes none of it; a write
belongs in the ops section, behind its approval rail.
"""
from __future__ import annotations

from typing import Any

from helix_codex_app.errors import PermissionDenied
from helix_codex_app.integration import cockpit_bridge, engine_bridge, packs
from helix_codex_app.modules.ops.service import workflow_card
from helix_codex_app.security.accounts import Account
from helix_codex_app.security.permissions import has_permission

COCKPIT_PERMISSION = "cockpit.view"
APPROVAL_QUEUE_LIMIT = 10

KPI_LABELS: dict[str, str] = {
    "active_athletes": "Active athletes",
    "mrr": "MRR (USD)",
    "attendance_rate": "Attendance (7d)",
    "churn_rate": "At-risk athletes",
    "facility_utilization": "Facility utilisation",
}
PERCENT_KEYS = ("attendance_rate", "facility_utilization")


def _format_value(key: str, value: Any) -> str:
    if value is None:
        return "—"
    if key in PERCENT_KEYS:
        return f"{float(value):.0%}"
    if key == "churn_rate":
        return str(int(value))
    if isinstance(value, (int, float)):
        return f"{value:,.0f}"
    return str(value)


def _format_target(key: str, value: Any) -> str:
    if value is None:
        return "—"
    if key in PERCENT_KEYS:
        return f"{float(value):.0%}"
    if isinstance(value, (int, float)):
        return f"{value:,.0f}"
    return str(value)


def owner_cards(summary: dict[str, Any]) -> list[dict[str, Any]]:
    """The five owner numbers, in the order the pack defines them.

    Two of the five do not come from the KPI block: attendance is the pack's own
    7-day figure and the at-risk count is the length of its at-risk list. Reading
    them from where the pack actually puts them is the whole point of not
    re-implementing the dashboard.
    """
    kpis = summary.get("kpis") or {}
    cards: list[dict[str, Any]] = []
    for key in cockpit_bridge.OWNER_KPI_ORDER:
        kpi = kpis.get(key) or {}
        if key == "attendance_rate":
            value = summary.get("attendance_7d")
        elif key == "churn_rate":
            value = len(summary.get("at_risk_athletes") or [])
        else:
            value = kpi.get("value")
        cards.append(
            {
                "key": key,
                "label": KPI_LABELS.get(key, key),
                "value": _format_value(key, value),
                "target": _format_target(key, kpi.get("target")),
                "met": kpi.get("met"),
            }
        )
    return cards


class CockpitService:
    """The cockpit's read-only views, each gated before it computes anything."""

    def owner(self, account: Account) -> dict[str, Any]:
        """The owner's board: five numbers, attendance, at-risk, approval queue."""
        self._require(account)
        summary = cockpit_bridge.owner_summary(account)
        approvals = engine_bridge.list_approvals(account)[:APPROVAL_QUEUE_LIMIT]
        return {
            "summary": summary,
            "cards": owner_cards(summary),
            "at_risk": list(summary.get("at_risk_athletes") or []),
            "enrollment": dict(summary.get("enrollment_pipeline") or {}),
            "sessions_total": summary.get("sessions_total"),
            "approval_queue": [workflow_card(w) for w in approvals],
            "data_mode": summary.get("data_mode", cockpit_bridge.DATA_MODE),
        }

    def summary(self, account: Account) -> dict[str, Any]:
        """The raw owner summary, for the JSON API."""
        self._require(account)
        return cockpit_bridge.owner_summary(account)

    def sections(self, account: Account) -> list[dict[str, Any]]:
        """The cockpit sections the installed packs contribute, gated as declared."""
        self._require(account)
        return [
            section
            for section in packs.all_sections()
            if has_permission(account, section["required_capability"])
        ]

    def landing(self, account: Account) -> dict[str, Any]:
        """Everything the cockpit landing page shows."""
        self._require(account)
        owner = self.owner(account)
        return {
            "cards": owner["cards"],
            "sections": self.sections(account),
            "data_mode": owner["data_mode"],
        }

    @staticmethod
    def _require(account: Account) -> None:
        if not has_permission(account, COCKPIT_PERMISSION):
            raise PermissionDenied(
                "the cockpit is for managers and owners",
                payload={
                    "account_id": account.account_id,
                    "role_id": account.role_id,
                    "permission": COCKPIT_PERMISSION,
                },
            )
