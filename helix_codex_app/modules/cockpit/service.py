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

from helix_codex_app.errors import NotFoundError, PermissionDenied
from helix_codex_app.integration import cockpit_bridge, engine_bridge
from helix_codex_app.modules.lowcode import section_registry
from helix_codex_app.modules.ops.service import workflow_card
from helix_codex_app.security.accounts import Account
from helix_codex_app.security.permissions import has_permission, permissions_for

COCKPIT_PERMISSION = "cockpit.view"
APPROVAL_QUEUE_LIMIT = 10
AUDIT_ENTRY_LIMIT = 20
AUDIT_SCAN_LIMIT = 200

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

    def sections(self, account: Account, conn) -> list[dict[str, Any]]:
        """The registered shell sections the account may see, gated as declared."""
        self._require(account)
        return section_registry.sections_for_permissions(conn, permissions_for(account, conn))

    def landing(self, account: Account, conn) -> dict[str, Any]:
        """Everything the cockpit landing page shows."""
        self._require(account)
        owner = self.owner(account)
        return {
            "cards": owner["cards"],
            "sections": self.sections(account, conn),
            "data_mode": owner["data_mode"],
        }

    def coach(self, account: Account, *, coach_id: str | None = None) -> dict[str, Any]:
        """One coach's day. With no coach chosen, the first one on the list."""
        self._require(account)
        options = cockpit_bridge.picker_options(account)["coaches"]
        selected = coach_id or (options[0]["id"] if options else "")
        if not selected:
            raise NotFoundError("no coaches are available in this workspace")
        summary = cockpit_bridge.coach_summary(account, coach_id=selected)
        return {
            "summary": summary,
            "options": options,
            "selected": selected,
            "data_mode": summary.get("data_mode", cockpit_bridge.DATA_MODE),
        }

    def parent(self, account: Account, *, family_id: str | None = None) -> dict[str, Any]:
        """One family's view. With no family chosen, the first one on the list."""
        self._require(account)
        options = cockpit_bridge.picker_options(account)["families"]
        selected = family_id or (options[0]["id"] if options else "")
        if not selected:
            raise NotFoundError("no families are available in this workspace")
        summary = cockpit_bridge.parent_summary(account, family_id=selected)
        return {
            "summary": summary,
            "options": options,
            "selected": selected,
            "data_mode": summary.get("data_mode", cockpit_bridge.DATA_MODE),
        }

    def control_plane(self, account: Account) -> dict[str, Any]:
        """Engine status, the halt state, and this workspace's recent audit rows.

        The audit panel is scoped to the account's own tenant by filtering the
        core's audit rows down to the correlation ids this workspace actually
        owns. The core keeps one audit store for the whole install, so an
        unfiltered panel would show one client another client's activity.
        """
        self._require(account)
        engine_bridge.authorize_read(account)
        owned = {
            workflow.correlation.correlation_id
            for workflow in engine_bridge.list_workflows(account, limit=AUDIT_SCAN_LIMIT)
        }
        entries = [
            row
            for row in engine_bridge.recent_audit_entries(limit=AUDIT_SCAN_LIMIT)
            if row.get("tenant_id") == account.tenant_id
            and (row.get("correlation_id") in owned or row.get("workflow_id") is None)
        ][:AUDIT_ENTRY_LIMIT]
        return {
            "engines": engine_bridge.list_engines(),
            "kill_switch": engine_bridge.kill_switch_status(account.tenant_id),
            "audit_entries": entries,
            "audit_chain_verified": engine_bridge.audit_chain_verified(),
            "data_mode": cockpit_bridge.DATA_MODE,
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
