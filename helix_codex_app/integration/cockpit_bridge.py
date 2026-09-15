"""The cockpit bridge: the capability pack's dashboards, computed in-process.

The pack already separates compute from render. Each view exposes a `compute_*`
function that returns a plain dictionary, and a thin `render_*` wrapper that only
wires that dictionary into Streamlit. This bridge calls the `compute_*` functions
and hands the dictionaries to Jinja, so the numbers on screen are the same numbers
the Streamlit app shows, and no dashboard logic is rewritten or duplicated.

Nothing here imports Streamlit, and nothing here is read from a screen. If a
figure cannot be computed the bridge raises rather than returning a partial
dashboard: a cockpit that quietly shows zeroes is worse than one that says it is
unavailable.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from helix_codex_app.errors import EngineUnavailableError, NotFoundError
from helix_codex_app.integration import policy_bridge
from helix_codex_app.security.accounts import Account

DEFAULT_PACK = "sports_academy"
DATA_MODE = "simulated_realistic"
# The cockpit rides on the operations GM's authority, because it is the operations
# surface for the people accountable for it. This is the third gate: the router
# dependency, the service check, and this policy call.
COCKPIT_CAPABILITY = "ops_execution"
COCKPIT_OWNING_ROLE = "ops_gm"
OWNER_KPI_ORDER: tuple[str, ...] = (
    "active_athletes",
    "mrr",
    "attendance_rate",
    "churn_rate",
    "facility_utilization",
)


def as_of_now() -> str:
    """The one clock this module uses, so every view agrees on the moment."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _pack_components(pack: str) -> tuple[Any, Any, Any]:
    """Import a pack's fixture builder, connector builder, and views.

    Imported lazily so a missing pack surfaces as a typed error at the point of
    use rather than breaking app startup.
    """
    try:
        import importlib

        module = importlib.import_module(f"capabilities.{pack}")
        contracts = importlib.import_module(f"capabilities.{pack}.contracts")
        owner_views = importlib.import_module(f"capabilities.{pack}.cockpit_views.owner_dashboard")
        coach_views = importlib.import_module(f"capabilities.{pack}.cockpit_views.coach_dashboard")
        parent_views = importlib.import_module(f"capabilities.{pack}.cockpit_views.parent_portal")
        from connectors.contracts import ConnectorContext
    except ImportError as exc:
        raise EngineUnavailableError(f"capability pack {pack!r} unavailable: {exc}") from exc
    return (
        module.build_synthetic_academy,
        contracts.build_academy_connectors,
        {
            "ConnectorContext": ConnectorContext,
            "owner": owner_views.compute_owner_dashboard,
            "coach": coach_views.compute_coach_dashboard,
            "parent": parent_views.compute_parent_view,
        },
    )


def _context(
    account: Account, *, as_of: str, pack: str
) -> tuple[Any, dict[str, Any], dict[str, Any]]:
    """Build the connector context and the read-only connectors for one tenant.

    The tenant and client come from the account, never from a request, so one
    workspace can never be shown another's numbers.
    """
    build_fixtures, build_connectors, views = _pack_components(pack)
    if not account.tenant_id or not account.client_id:
        raise EngineUnavailableError(
            "cockpit: the account has no tenant and client, so no pack data can be scoped"
        )
    policy_bridge.authorize_engine_call(
        account,
        capability=COCKPIT_CAPABILITY,
        action="read",
        owning_role_id=COCKPIT_OWNING_ROLE,
    )
    context = views["ConnectorContext"](
        account.tenant_id,
        account.domain_id,
        account.client_id,
        actor=account.account_id,
        correlation_id=f"cockpit-{account.account_id}",
        data_mode=DATA_MODE,
    )
    fixtures = build_fixtures(account.tenant_id, account.client_id, as_of)
    return context, build_connectors(context, fixtures), {"views": views, "fixtures": fixtures}


def owner_summary(account: Account, *, as_of: str | None = None, pack: str = DEFAULT_PACK) -> dict:
    """The owner's numbers for this account's workspace."""
    moment = as_of or as_of_now()
    context, connectors, extra = _context(account, as_of=moment, pack=pack)
    summary = extra["views"]["owner"](context, connectors, moment)
    summary.setdefault("data_mode", DATA_MODE)
    return summary


def coach_summary(
    account: Account,
    *,
    coach_id: str,
    as_of: str | None = None,
    pack: str = DEFAULT_PACK,
) -> dict:
    """One coach's day. An unknown coach is a typed error, not an empty board."""
    moment = as_of or as_of_now()
    context, connectors, extra = _context(account, as_of=moment, pack=pack)
    summary = extra["views"]["coach"](context, connectors, moment, coach_id)
    if summary.get("error"):
        raise NotFoundError(
            f"no such coach {coach_id!r}",
            payload={"coach_id": coach_id, "reason": summary["error"]},
        )
    return summary


def parent_summary(
    account: Account,
    *,
    family_id: str,
    as_of: str | None = None,
    pack: str = DEFAULT_PACK,
) -> dict:
    """One family's read-only view. An unknown family is a typed error."""
    moment = as_of or as_of_now()
    context, connectors, extra = _context(account, as_of=moment, pack=pack)
    summary = extra["views"]["parent"](context, connectors, moment, family_id)
    if summary.get("error"):
        raise NotFoundError(
            f"no such family {family_id!r}",
            payload={"family_id": family_id, "reason": summary["error"]},
        )
    return summary


def picker_options(
    account: Account, *, pack: str = DEFAULT_PACK
) -> dict[str, list[dict[str, str]]]:
    """The coaches and families the pickers offer, for this workspace only."""
    moment = as_of_now()
    _context_value, _connectors, extra = _context(account, as_of=moment, pack=pack)
    fixtures = extra["fixtures"]
    return {
        "coaches": [
            {"id": coach.coach_id, "label": getattr(coach, "name", coach.coach_id)}
            for coach in fixtures.get("coaches", [])
        ],
        "families": [
            {"id": family.family_id, "label": getattr(family, "name", family.family_id)}
            for family in fixtures.get("families", [])
        ],
    }
