"""
Helix Codex OS — Enterprise Organization Model & Control Plane Governance Framework.

Implements the two non-negotiable architectural layers of the enterprise
organization model specification.

A. Context optimization via strongly-typed data contracts.
   No agent or engine may pass raw strings or unchecked dictionaries across code
   boundaries. Every transaction is wrapped in an immutable data contract carrying
   explicit correlation meta-arrays, so any process can read an active pipeline and
   extract its telemetry, authority tracking and logic tree without string parsing.

B. Functional architecture of bounded autonomy.
   Agents may only propose and prepare operational or financial actions. Any task
   crossing a defined risk boundary is frozen in an explicit state machine and held
   in the local SQLite store until an authorized human commits a validation token.

Maintenance notes
-----------------
* ORGANIZATION_CATALOG below is the *control-plane runtime authority* for financial
  approval gating: ``owned_engines``, ``allowed_data_classifications``, ``kpis``,
  ``oversight_only`` and the financial enforcement ceiling are declared here.
* Structural role data (capabilities, tools, peer calls, segregation of duties) is
  **sourced from** ``organization/role-catalog.yaml`` at import — it is not mirrored
  here. ``detect_catalog_drift()`` compares the live file against the imported
  snapshot so a stale in-process catalog is visible rather than silent.
* The runtime authorizers (``contracts.adapter``, ``security.policy``,
  ``control_plane.engine``) all read the YAML catalog's ``roles_by_id`` directly.
  They never read ``RoleSpec``'s structural fields, which is why sourcing those
  fields from the YAML cannot change an authorisation decision.
* The contract models in this module SUBCLASS the canonical ``contracts.task`` models
  rather than redefining them. A governance ``TaskRequest`` therefore stays a valid
  input to ``control_plane.engine.Engine.submit()``: one type, one validation path,
  no parallel drift.
"""
from __future__ import annotations

import datetime
import hashlib
import json
import re
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, FrozenSet, List, Optional, Tuple

from contracts.task import (
    CorrelationContext as _BaseCorrelationContext,
)
from contracts.task import (
    TaskRequest as _BaseTaskRequest,
)
from contracts.task import (
    TaskResult as _BaseTaskResult,
)
from control_plane.store import Store
from control_plane.workflow import WorkflowState, is_valid_transition
from security.classification import DataClassification

SCHEMA_VERSION = "1.0"

#: Minimum confidence required for a task to run without human validation.
#: Below this line the task is frozen in AWAITING_APPROVAL (fail-closed).
MIN_AUTONOMY_CONFIDENCE = 0.75

_UUID4_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


# ── validation helpers ─────────────────────────────────────────────────────


def _require_non_empty_str(value: Any, field_path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_path}: must be non-empty string, got {value!r}")
    return value.strip()


def _require_uuid4(value: Any, field_path: str) -> str:
    s = _require_non_empty_str(value, field_path)
    if not _UUID4_RE.match(s):
        raise ValueError(f"{field_path}: must be a canonical UUID4 string, got {s!r}")
    return s


def _require_money(value: Any, field_path: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field_path}: must be a number, got {type(value).__name__}")
    f = float(value)
    if f < 0:
        raise ValueError(f"{field_path}: must be >= 0, got {f}")
    if f != f or f in (float("inf"), float("-inf")):
        raise ValueError(f"{field_path}: must be finite, got {f!r}")
    return round(f, 2)


def _require_confidence(value: Any, field_path: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(
            f"{field_path}: confidence must be number 0.0-1.0, got {type(value).__name__}"
        )
    f = float(value)
    if not (0.0 <= f <= 1.0):
        raise ValueError(f"{field_path}: confidence must be 0.0-1.0, got {f}")
    return f


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")


def _canonical_json(payload: Any) -> str:
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str
    )


def _sha256(payload: Any) -> str:
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


# ── errors ─────────────────────────────────────────────────────────────────


class AccessDeniedError(PermissionError):
    """
    Raised when a task requests an engine outside the active actor's owned_engines.

    Subclasses PermissionError so callers that only catch OSError-grade security
    failures still trap it, while contract-level callers can catch it precisely.
    """

    def __init__(self, actor_id: str, role_id: str, engine: str, owned: Tuple[str, ...]) -> None:
        self.actor_id = actor_id
        self.role_id = role_id
        self.engine = engine
        self.owned = tuple(owned)
        super().__init__(
            f"Access Denied: actor {actor_id!r} (role {role_id!r}) requested engine {engine!r}, "
            f"owned_engines={list(self.owned)}"
        )


class GovernanceStateError(ValueError):
    """Raised when a governed task cannot legally move to the requested state."""


# ── canonical organization catalog ─────────────────────────────────────────


@dataclass(frozen=True)
class RoleSpec:
    """
    Immutable profile for one seat in the enterprise organization catalog.

    financial_approval_limit_usd is the fail-closed boundary: any task whose
    estimated cost crosses it is frozen for human validation. ``None`` means
    unlimited (SAMI only, and only via human escalation).

    The structural fields (owned_capabilities, allowed_tools, allowed_peer_calls,
    segregation_of_duties) are sourced from organization/role-catalog.yaml at import
    and are read only by detect_catalog_drift(). Authorisation decisions read the
    YAML catalog directly, so these fields are drift telemetry rather than
    enforcement inputs.
    """

    role_id: str
    display_name: str
    mission: str
    owned_engines: Tuple[str, ...]
    allowed_data_classifications: Tuple[str, ...]
    financial_approval_limit_usd: Optional[float]
    kpis: Tuple[str, ...]
    oversight_only: bool = False
    # Structural fields sourced from YAML — used for drift detection.
    owned_capabilities: Tuple[str, ...] = ()
    allowed_tools: Tuple[str, ...] = ()
    allowed_peer_calls: Tuple[str, ...] = ()
    segregation_of_duties: Tuple[Tuple[str, ...], Tuple[str, ...]] = ()  # (must_review, can_review)

    def __post_init__(self) -> None:
        if not self.role_id:
            raise ValueError("RoleSpec.role_id: must be non-empty")
        if self.financial_approval_limit_usd is not None:
            _require_money(
                self.financial_approval_limit_usd,
                f"RoleSpec[{self.role_id}].financial_approval_limit_usd",
            )
        unknown = [c for c in self.allowed_data_classifications if c not in DataClassification.ALL]
        if unknown:
            raise ValueError(
                f"RoleSpec[{self.role_id}].allowed_data_classifications: unknown labels {unknown} "
                f"(allowed: {sorted(DataClassification.ALL)})"
            )

    def can_read(self, classification: str) -> bool:
        return classification in self.allowed_data_classifications

    def owns_engine(self, engine: Optional[str]) -> bool:
        if engine is None:
            return True
        return normalize_engine(engine) in {normalize_engine(e) for e in self.owned_engines}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "role_id": self.role_id,
            "display_name": self.display_name,
            "mission": self.mission,
            "owned_engines": list(self.owned_engines),
            "allowed_data_classifications": list(self.allowed_data_classifications),
            "financial_approval_limit_usd": self.financial_approval_limit_usd,
            "kpis": list(self.kpis),
            "oversight_only": self.oversight_only,
        }

    # Mapping-style access keeps the catalog convenient for adapters that consume
    # JSON-shaped role records without exposing a mutable dictionary internally.
    def __getitem__(self, key: str) -> Any:
        aliases = {
            "id": "role_id",
            "owned_engines": "owned_engines",
            "allowed_data_classifications": "allowed_data_classifications",
            "financial_approval_limit": "financial_approval_limit_usd",
            "financial_approval_limit_usd": "financial_approval_limit_usd",
        }
        field_name = aliases.get(key, key)
        if not hasattr(self, field_name):
            raise KeyError(key)
        value = getattr(self, field_name)
        return list(value) if isinstance(value, tuple) else value

    def get(self, key: str, default: Any = None) -> Any:
        try:
            return self[key]
        except KeyError:
            return default


_ALL_ENGINES: Tuple[str, ...] = ("wfm", "rta", "cx", "crm", "b2b", "personnel", "control_plane")
_ALL_CLASSIFICATIONS: Tuple[str, ...] = (
    DataClassification.PUBLIC,
    DataClassification.INTERNAL,
    DataClassification.CLIENT_CONFIDENTIAL,
    DataClassification.PERSONNEL_SENSITIVE,
    DataClassification.FINANCIAL,
    DataClassification.REGULATED_HIGH_RISK,
)

#: Runtime role id -> YAML role id. The runtime catalog renamed ``fraud_revenue_gm``
#: after ``organization/role-catalog.yaml`` was authored; the rename is documented in
#: ``organization/gm_activation.py``. Structural fields for the renamed seat are read
#: from the YAML entry it aliases.
YAML_ROLE_ALIASES: Dict[str, str] = {"fraud_revenue_gm": "fraud_gm"}


class RoleCatalogUnavailableError(RuntimeError):
    """
    Raised when organization/role-catalog.yaml cannot be read while building the
    runtime catalog.

    Fail closed. The four structural fields are *derived* from the YAML rather than
    mirrored here, so a governance layer that cannot read its own source of truth
    must refuse to start rather than come up with an empty capability map that would
    silently authorise nothing (or, worse, everything).
    """


def _structural_role_fields() -> Dict[str, Dict[str, Any]]:
    """
    Read the structural role fields from organization/role-catalog.yaml.

    The four fields returned per role — ``owned_capabilities``, ``allowed_tools``,
    ``allowed_peer_calls`` and ``segregation_of_duties`` — are the ones the YAML owns
    outright. The runtime catalog used to carry hand-copied duplicates of all four and
    ``detect_catalog_drift()`` existed to notice when the copies rotted; deriving them
    removes the copy instead of policing it.

    The remaining ``RoleSpec`` fields stay hand-written on purpose:

    * ``owned_engines`` / ``allowed_data_classifications`` — the YAML's
      ``readable_data_domains`` is a different vocabulary (domains, not
      ``DataClassification`` labels), so it cannot be projected onto them.
    * ``kpis`` — the YAML list is the shared org-chart vocabulary; the runtime list is
      the seat's own enforcement set.
    * ``display_name`` / ``mission`` — the runtime strings are deliberately terser
      than the YAML prose.
    * ``oversight_only`` — runtime-only concept, absent from the YAML schema.
    * ``financial_approval_limit_usd`` — the runtime value is the *enforcement
      ceiling* and is deliberately stricter than the YAML org-chart authority; see
      :data:`FINANCIAL_LIMIT_OVERRIDES`.

    Raises:
        RoleCatalogUnavailableError: the YAML is unreadable, malformed, or missing a
            seat the runtime catalog needs.
    """
    from organization.role_catalog import load_role_catalog

    try:
        yaml_catalog = load_role_catalog("organization/role-catalog.yaml")
    except Exception as exc:
        raise RoleCatalogUnavailableError(
            "cannot read organization/role-catalog.yaml, which owns the structural "
            f"role fields (owned_capabilities, allowed_tools, allowed_peer_calls, "
            f"segregation_of_duties): {exc}"
        ) from exc

    yaml_roles: Dict[str, Any] = yaml_catalog.get("roles_by_id", {})

    # Index by *runtime* id. The two catalogs disagree on exactly one seat's name
    # (YAML fraud_gm, runtime fraud_revenue_gm), so the alias is resolved here and the
    # rest of the module never has to know.
    by_runtime_id: Dict[str, Any] = dict(yaml_roles)
    for runtime_id, yaml_id in YAML_ROLE_ALIASES.items():
        if yaml_id in yaml_roles:
            by_runtime_id[runtime_id] = yaml_roles[yaml_id]

    return {
        role_id: {
            "owned_capabilities": tuple(role.get("owned_capabilities") or ()),
            "allowed_tools": tuple(role.get("allowed_tools") or ()),
            "allowed_peer_calls": tuple(role.get("allowed_peer_calls") or ()),
            "segregation_of_duties": (
                tuple((role.get("segregation_of_duties") or {}).get("must_be_reviewed_by") or ()),
                tuple((role.get("segregation_of_duties") or {}).get("can_review") or ()),
            ),
        }
        for role_id, role in by_runtime_id.items()
    }


#: Structural fields for every seat, resolved once at import.
_STRUCTURAL_FIELDS: Dict[str, Dict[str, Any]] = _structural_role_fields()


def _structural(role_id: str) -> Dict[str, Any]:
    """
    Structural fields for one runtime seat, or a fail-closed error.

    Called once per seat while building ``_ROLE_CATALOG``, so a seat that exists in
    the runtime catalog but not in the YAML fails the import rather than silently
    getting an empty capability set.
    """
    try:
        return _STRUCTURAL_FIELDS[role_id]
    except KeyError:
        raise RoleCatalogUnavailableError(
            f"role {role_id!r} has no structural entry in organization/role-catalog.yaml "
            f"(known runtime ids: {sorted(_STRUCTURAL_FIELDS)})"
        ) from None


# ── runtime financial enforcement ceilings ─────────────────────────────────
#
# These are a *policy decision*, not drift. organization/role-catalog.yaml is the
# org chart: what each seat is entitled to authorise. The values below are what the
# platform actually lets a seat authorise before freezing the task for a human.
#
# Every entry narrows authority relative to the org chart; none widens it.
# ``tests/test_c1_contracts.py::test_catalog_drift_runtime_limits_never_exceed_yaml_authority``
# proves the narrowing, and ``scripts/check_governance_drift.py`` fails CI if the set
# of overriding seats changes.

#: Seats whose runtime ceiling is deliberately stricter than the YAML authority.
#: Declared here rather than left to be discovered by comparing two files.
FINANCIAL_LIMIT_OVERRIDES: Dict[str, Optional[float]] = {
    "ops_gm": 500.00,
    "compliance_quality_gm": 0.00,
    "fraud_revenue_gm": 0.00,
    "hr_personnel_gm": 1_000.00,
    "ld_gm": 200.00,
    "sales_gm": 2_500.00,
    "marketing_gm": 500.00,
    "ict_gm": 5_000.00,
}

#: Seats whose runtime ceiling is unlimited — reachable only through human
#: escalation. Declared separately from the override map so that "no override
#: applies" and "explicitly unlimited" remain different statements.
UNLIMITED_FINANCIAL_ROLES: FrozenSet[str] = frozenset({"sami"})

#: The seats whose runtime ceiling overrides the YAML. Derived from
#: :data:`FINANCIAL_LIMIT_OVERRIDES` rather than hand-maintained, so the declaration
#: and the accepted-drift pin cannot disagree.
ACCEPTED_FINANCIAL_DRIFT_ROLES: FrozenSet[str] = frozenset(FINANCIAL_LIMIT_OVERRIDES)


def _financial_limit(role_id: str) -> Optional[float]:
    """
    Runtime enforcement ceiling for one seat, or a fail-closed error.

    Called once per seat while building ``_ROLE_CATALOG``. A seat that declares
    neither an override nor an unlimited ceiling fails the import, so a newly added
    seat cannot silently inherit "unlimited" authority by omission.
    """
    if role_id in FINANCIAL_LIMIT_OVERRIDES:
        return FINANCIAL_LIMIT_OVERRIDES[role_id]
    if role_id in UNLIMITED_FINANCIAL_ROLES:
        return None
    raise RoleCatalogUnavailableError(
        f"role {role_id!r} declares no runtime financial ceiling; every seat must "
        f"appear in FINANCIAL_LIMIT_OVERRIDES or UNLIMITED_FINANCIAL_ROLES"
    )


#: Canonical Organization Catalog & Role Matrix (8 Functional GMs + SAMI).
#:
#: Authority fields (what the runtime owns and the YAML does not) are literal here.
#: Structural fields are spliced in from the YAML via ``**_structural(role_id)`` so
#: there is exactly one copy of them in the tree.
_ROLE_CATALOG: Dict[str, RoleSpec] = {
    "sami": RoleSpec(
        role_id="sami",
        display_name="SAMI — Executive Coordinator / CEO",
        mission=(
            "Executive coordination; sets strategy, overrides conflicts, signs off on system "
            "north star. Cross-system master orchestrator."
        ),
        owned_engines=_ALL_ENGINES,
        allowed_data_classifications=_ALL_CLASSIFICATIONS,
        financial_approval_limit_usd=_financial_limit("sami"),  # unlimited, human-escalated only
        kpis=("system_health", "operational_margin"),
        **_structural("sami"),
    ),
    "ops_gm": RoleSpec(
        role_id="ops_gm",
        display_name="OPS_GM — Contact Centre Operations",
        mission="Contact-centre execution, queue health, floor performance management.",
        owned_engines=("wfm", "rta", "cx"),
        allowed_data_classifications=(
            DataClassification.INTERNAL,
            DataClassification.CLIENT_CONFIDENTIAL,
        ),
        financial_approval_limit_usd=_financial_limit("ops_gm"),
        kpis=("sla", "service_level", "occupancy", "adherence", "aht"),
        **_structural("ops_gm"),
    ),
    "compliance_quality_gm": RoleSpec(
        role_id="compliance_quality_gm",
        display_name="COMPLIANCE_QUALITY_GM — Policy & Quality Assurance",
        mission=(
            "Policy enforcement, QA sampling, risk controls, evidence generation, escalation. "
            "Cross-system control plane, oversight only."
        ),
        owned_engines=(),  # oversight only: proposes, never executes
        allowed_data_classifications=_ALL_CLASSIFICATIONS,
        financial_approval_limit_usd=_financial_limit("compliance_quality_gm"),
        kpis=("quality_score", "compliance_drift"),
        oversight_only=True,
        **_structural("compliance_quality_gm"),
    ),
    "fraud_revenue_gm": RoleSpec(
        role_id="fraud_revenue_gm",
        display_name="FRAUD_REVENUE_GM — Revenue Assurance",
        mission="Leakage prevention, abuse tracking, anomaly detection, revenue assurance protection.",
        owned_engines=("crm", "b2b"),
        allowed_data_classifications=(
            DataClassification.INTERNAL,
            DataClassification.CLIENT_CONFIDENTIAL,
            DataClassification.FINANCIAL,
        ),
        financial_approval_limit_usd=_financial_limit("fraud_revenue_gm"),
        kpis=("leakage", "anomaly_delta"),
        **_structural("fraud_revenue_gm"),
    ),
    "hr_personnel_gm": RoleSpec(
        role_id="hr_personnel_gm",
        display_name="HR_PERSONNEL_GM — People Lifecycle",
        mission="People lifecycle management, staffing requisitions, corporate workforce policies.",
        owned_engines=("personnel", "wfm"),
        allowed_data_classifications=(
            DataClassification.INTERNAL,
            DataClassification.PERSONNEL_SENSITIVE,
        ),
        financial_approval_limit_usd=_financial_limit("hr_personnel_gm"),
        kpis=("turnover_rate", "time_to_hire"),
        **_structural("hr_personnel_gm"),
    ),
    "ld_gm": RoleSpec(
        role_id="ld_gm",
        display_name="LD_GM — Learning & Development",
        mission="Employee competency tracking, training, workforce knowledge transfer.",
        owned_engines=("wfm",),  # "wfont" in the source matrix — see ENGINE_ALIASES
        allowed_data_classifications=(
            DataClassification.INTERNAL,
            DataClassification.PERSONNEL_SENSITIVE,
        ),
        financial_approval_limit_usd=_financial_limit("ld_gm"),
        kpis=("competency_score", "time_to_competency"),
        **_structural("ld_gm"),
    ),
    "sales_gm": RoleSpec(
        role_id="sales_gm",
        display_name="SALES_GM — Revenue Execution",
        mission="Pipeline tracking, qualification, proposals, corporate revenue execution.",
        owned_engines=("crm", "b2b"),
        allowed_data_classifications=(
            DataClassification.INTERNAL,
            DataClassification.CLIENT_CONFIDENTIAL,
        ),
        financial_approval_limit_usd=_financial_limit("sales_gm"),
        kpis=("pipeline_value", "win_rate"),
        **_structural("sales_gm"),
    ),
    "marketing_gm": RoleSpec(
        role_id="marketing_gm",
        display_name="MARKETING_GM — Market Intelligence & Demand",
        mission="Market intelligence, campaign execution, corporate positioning, demand generation.",
        owned_engines=("crm",),
        allowed_data_classifications=(
            DataClassification.PUBLIC,
            DataClassification.INTERNAL,
        ),
        financial_approval_limit_usd=_financial_limit("marketing_gm"),
        kpis=("cac", "lead_volume"),
        **_structural("marketing_gm"),
    ),
    "ict_gm": RoleSpec(
        role_id="ict_gm",
        display_name="ICT_GM — Platform & Infrastructure",
        mission="Platform uptime, integrations, data security, reliability, infrastructure operations.",
        owned_engines=("control_plane",),
        allowed_data_classifications=(
            DataClassification.INTERNAL,
            DataClassification.REGULATED_HIGH_RISK,
        ),
        financial_approval_limit_usd=_financial_limit("ict_gm"),
        kpis=("engine_latency", "model_timeout"),
        **_structural("ict_gm"),
    ),
}


class _OrganizationCatalog(dict):
    """Case-insensitive catalog view with immutable RoleSpec values."""

    @staticmethod
    def _key(key: Any) -> Any:
        return key.lower() if isinstance(key, str) else key

    def __getitem__(self, key: Any) -> RoleSpec:
        return super().__getitem__(self._key(key))

    def get(self, key: Any, default: Any = None) -> Any:
        return super().get(self._key(key), default)

    def __contains__(self, key: object) -> bool:
        return super().__contains__(self._key(key))


ORGANIZATION_CATALOG: Dict[str, RoleSpec] = _OrganizationCatalog(_ROLE_CATALOG)

#: Source matrix uses shorthand engine names; normalize before comparison.
ENGINE_ALIASES: Dict[str, str] = {
    "wfont": "wfm",  # WILI/LD alignment shorthand in the role matrix
    "wf": "wfm",
    "cx_engine": "cx",
    "crm_engine": "crm",
    "b2b_engine": "b2b",
    "personnel_engine": "personnel",
    "runtime": "control_plane",
    "control-plane": "control_plane",
}

#: Crew display names -> catalog role ids (existing runtime agents).
ACTOR_ALIASES: Dict[str, str] = {
    "sami": "sami",
    "suby": "ops_gm",
    "phili": "hr_personnel_gm",
    "wili": "ld_gm",
    "maya": "marketing_gm",
    "liza": "sales_gm",
    "andy": "compliance_quality_gm",
    "tomy": "ict_gm",
    "nono": "fraud_revenue_gm",
}


def normalize_engine(engine: str) -> str:
    """Normalize an engine identifier (aliases, case, separators)."""
    e = _require_non_empty_str(engine, "normalize_engine.engine").lower().strip()
    e = e.replace("-", "_").replace(" ", "_")
    return ENGINE_ALIASES.get(e, e)


def get_role(role_id: str) -> RoleSpec:
    """Look up a role in the canonical catalog. Unknown role -> ValueError (fail closed)."""
    key = _require_non_empty_str(role_id, "get_role.role_id").lower().strip()
    try:
        return ORGANIZATION_CATALOG[key]
    except KeyError:
        raise ValueError(
            f"get_role: unknown role_id {role_id!r} (catalog: {sorted(ORGANIZATION_CATALOG)})"
        ) from None


def resolve_actor_role(actor_id: str, fallback_role_id: Optional[str] = None) -> str:
    """
    Map an actor identifier (agent name, crew name or role id) to a catalog role id.

    Unknown actors fall back to ``fallback_role_id`` (normally the request's
    owning_role_id, i.e. the actor is acting on that role's behalf). If neither
    resolves, returns "" and the caller must fail closed.
    """
    key = _require_non_empty_str(actor_id, "resolve_actor_role.actor_id").lower().strip()
    if key in ORGANIZATION_CATALOG:
        return key
    if key in ACTOR_ALIASES:
        return ACTOR_ALIASES[key]
    if fallback_role_id:
        fb = fallback_role_id.lower().strip()
        if fb in ORGANIZATION_CATALOG:
            return fb
    return ""


#: The accepted-drift set is declared up with the ceilings it describes — see
#: :data:`FINANCIAL_LIMIT_OVERRIDES` and :data:`ACCEPTED_FINANCIAL_DRIFT_ROLES`.


def detect_catalog_drift() -> List[Dict[str, Any]]:
    """
    Report divergence between this runtime catalog and organization/role-catalog.yaml.

    Five fields are compared. They now fall into two distinct classes, and the
    distinction matters when reading a report:

    * ``financial_approval_limit_usd`` — a **genuine, intentional divergence**. The
      runtime value is the enforcement ceiling and is deliberately stricter than the
      YAML org-chart authority. Exactly the eight seats in
      :data:`ACCEPTED_FINANCIAL_DRIFT_ROLES` diverge, and each is declared in
      :data:`FINANCIAL_LIMIT_OVERRIDES`.
    * ``owned_capabilities`` / ``allowed_tools`` / ``allowed_peer_calls`` /
      ``segregation_of_duties`` — **derived** from the YAML at import (see
      :func:`_structural_role_fields`), so these entries are no longer a
      mirror-divergence signal. A hit here means the file changed on disk *after*
      this process imported the catalog, i.e. the in-memory authority is stale. That
      is a restart-worthy condition, and it still fails CI.

    Callers that need to distinguish accepted divergence from regression should
    compare the result against :data:`ACCEPTED_FINANCIAL_DRIFT_ROLES`; see
    ``scripts/check_governance_drift.py``.
    """

    def _field(y: Dict[str, Any], r: Any, key: str, normalize: bool = False) -> None:
        y_val = y.get(key)
        r_val = r
        if normalize:
            y_val = tuple(y_val or ())
        if y_val != r_val:
            drift.append(
                {
                    "role_id": role_id,
                    "field": key,
                    "runtime": list(r_val) if isinstance(r_val, tuple) else r_val,
                    "yaml": list(y_val) if isinstance(y_val, tuple) else y_val,
                    "detail": f"{key} differs between runtime catalog and role-catalog.yaml",
                }
            )

    drift: List[Dict[str, Any]] = []
    try:
        from organization.role_catalog import load_role_catalog

        yaml_catalog = load_role_catalog("organization/role-catalog.yaml")
    except Exception as exc:  # pragma: no cover - environment dependent
        return [
            {
                "role_id": "*",
                "field": "role-catalog.yaml",
                "runtime": None,
                "yaml": None,
                "detail": str(exc),
            }
        ]

    yaml_roles = yaml_catalog.get("roles_by_id", {})
    for role_id, spec in ORGANIZATION_CATALOG.items():
        y = yaml_roles.get(role_id) or yaml_roles.get(YAML_ROLE_ALIASES.get(role_id, ""))
        if y is None:
            drift.append(
                {
                    "role_id": role_id,
                    "field": "presence",
                    "runtime": role_id,
                    "yaml": None,
                    "detail": "role present in runtime catalog but missing from role-catalog.yaml",
                }
            )
            continue
        y_sod = y.get("segregation_of_duties") or {}
        _field(y, spec.owned_capabilities, "owned_capabilities", normalize=True)
        _field(y, spec.allowed_tools, "allowed_tools", normalize=True)
        _field(y, spec.allowed_peer_calls, "allowed_peer_calls", normalize=True)
        r_sod = spec.segregation_of_duties or ((), ())
        y_sod_val = (
            tuple(y_sod.get("must_be_reviewed_by") or ()),
            tuple(y_sod.get("can_review") or ()),
        )
        if y_sod_val != r_sod:
            drift.append(
                {
                    "role_id": role_id,
                    "field": "segregation_of_duties",
                    "runtime": [list(r_sod[0]), list(r_sod[1])],
                    "yaml": [list(y_sod_val[0]), list(y_sod_val[1])],
                    "detail": "segregation_of_duties differs between runtime catalog and role-catalog.yaml",
                }
            )
        y_limit = (y.get("approval_limits") or {}).get("max_financial_amount")
        r_limit = spec.financial_approval_limit_usd
        if y_limit != r_limit:
            drift.append(
                {
                    "role_id": role_id,
                    "field": "financial_approval_limit_usd",
                    "runtime": r_limit,
                    "yaml": y_limit,
                    "detail": "financial approval limit differs between runtime catalog and role-catalog.yaml",
                }
            )
    return drift


# ── contract layer: correlation / request / result ──────────────────────────


@dataclass
class CorrelationContext(_BaseCorrelationContext):
    """
    Governance correlation meta-array.

    Extends the canonical contract with ``actor_id`` and enforces a strict UUID4
    correlation id, so any process can join telemetry, authority and audit rows
    without parsing strings.
    """

    actor_id: Optional[str] = None

    def __post_init__(self) -> None:
        super().__post_init__()
        self.correlation_id = _require_uuid4(
            self.correlation_id, "CorrelationContext.correlation_id"
        )
        if self.actor_id is not None:
            self.actor_id = _require_non_empty_str(self.actor_id, "CorrelationContext.actor_id")

    def to_dict(self) -> Dict[str, Any]:
        d = super().to_dict()
        d["actor_id"] = self.actor_id
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CorrelationContext":
        if not isinstance(data, dict):
            raise ValueError(
                f"CorrelationContext.from_dict: expected dict, got {type(data).__name__}"
            )
        base = _BaseCorrelationContext.from_dict(data)
        return cls(
            correlation_id=base.correlation_id,
            idempotency_key=base.idempotency_key,
            tenant_id=base.tenant_id,
            client_id=base.client_id,
            created_at=base.created_at,
            schema_version=base.schema_version,
            trace_parent=base.trace_parent,
            actor_id=data.get("actor_id"),
        )

    @classmethod
    def new(
        cls,
        tenant_id: Optional[str] = None,
        client_id: Optional[str] = None,
        actor_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> "CorrelationContext":
        now = _now_iso()
        return cls(
            correlation_id=correlation_id or str(uuid.uuid4()),
            idempotency_key=idempotency_key or str(uuid.uuid4()),
            tenant_id=tenant_id,
            client_id=client_id,
            created_at=now,
            actor_id=actor_id,
        )


@dataclass
class TaskRequest(_BaseTaskRequest):
    """
    Master request contract for the governed control plane.

    Adds the bounded-autonomy parameters to the canonical request:
      * ``target_engine``      — engine the task wants to run on (ownership gate)
      * ``estimated_financial_cost`` — USD exposure of the proposed action
      * ``confidence_score``   — model/agent confidence in the proposal
      * ``requested_data_classification`` — highest classification touched

    The post-initialization validator enforces the ownership gate: a task naming an
    engine that is not in the active actor's owned_engines array raises
    AccessDeniedError immediately.
    """

    target_engine: Optional[str] = None
    estimated_financial_cost: float = 0.0
    confidence_score: float = 1.0
    requested_data_classification: str = DataClassification.INTERNAL

    def __post_init__(self) -> None:
        super().__post_init__()

        if self.target_engine is not None:
            self.target_engine = normalize_engine(self.target_engine)
        self.estimated_financial_cost = _require_money(
            self.estimated_financial_cost, "TaskRequest.estimated_financial_cost"
        )
        self.confidence_score = _require_confidence(
            self.confidence_score, "TaskRequest.confidence_score"
        )
        if self.requested_data_classification not in DataClassification.ALL:
            raise ValueError(
                f"TaskRequest.requested_data_classification: unknown classification "
                f"{self.requested_data_classification!r} (allowed: {sorted(DataClassification.ALL)})"
            )

        # ── ownership gate (fail-closed, runs on every construction) ──
        if self.target_engine is not None:
            role_id = resolve_actor_role(self.requesting_actor, self.owning_role_id)
            if not role_id:
                raise AccessDeniedError(
                    self.requesting_actor, "<unresolved>", self.target_engine, ()
                )
            spec = get_role(role_id)
            if not spec.owns_engine(self.target_engine):
                raise AccessDeniedError(
                    self.requesting_actor, role_id, self.target_engine, spec.owned_engines
                )

    # Convenience: actor_id is the canonical contract's requesting_actor.
    @property
    def actor_id(self) -> str:
        return self.requesting_actor

    def to_dict(self) -> Dict[str, Any]:
        d = super().to_dict()
        d.update(
            {
                "target_engine": self.target_engine,
                "estimated_financial_cost": self.estimated_financial_cost,
                "confidence_score": self.confidence_score,
                "requested_data_classification": self.requested_data_classification,
            }
        )
        return d


@dataclass
class TaskResult(_BaseTaskResult):
    """
    Master result contract for the governed control plane.

    Carries the resolved control-plane state so a caller can tell the difference
    between a computed engine result and a task that is frozen pending a human.
    """

    workflow_state: Optional[str] = None
    financial_cost_usd: Optional[float] = None
    governance_decision: Optional[str] = None

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.workflow_state is not None and self.workflow_state not in WorkflowState.ALL:
            raise ValueError(
                f"TaskResult.workflow_state: must be one of {sorted(WorkflowState.ALL)}, got {self.workflow_state!r}"
            )
        if self.financial_cost_usd is not None:
            self.financial_cost_usd = _require_money(
                self.financial_cost_usd, "TaskResult.financial_cost_usd"
            )
        if self.governance_decision is not None:
            self.governance_decision = _require_non_empty_str(
                self.governance_decision, "TaskResult.governance_decision"
            )

    @property
    def confidence_score(self) -> Optional[float]:
        """Alias for the canonical ``confidence`` field (shared vocabulary)."""
        return self.confidence

    def to_dict(self) -> Dict[str, Any]:
        d = super().to_dict()
        d.update(
            {
                "workflow_state": self.workflow_state,
                "financial_cost_usd": self.financial_cost_usd,
                "governance_decision": self.governance_decision,
            }
        )
        return d


# ── bounded autonomy: the fail-closed gate ─────────────────────────────────


@dataclass(frozen=True)
class GovernanceDecision:
    """Typed outcome of a bounded-autonomy evaluation."""

    allowed: bool
    requires_human_approval: bool
    reason_code: str
    reason: str
    state: str
    estimated_cost_usd: float
    limit_usd: Optional[float]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "allowed": self.allowed,
            "requires_human_approval": self.requires_human_approval,
            "reason_code": self.reason_code,
            "reason": self.reason,
            "state": self.state,
            "estimated_cost_usd": self.estimated_cost_usd,
            "limit_usd": self.limit_usd,
        }


def evaluate_gate(
    role_id: str,
    *,
    estimated_financial_cost: float = 0.0,
    data_classification: str = DataClassification.INTERNAL,
    confidence_score: float = 1.0,
    target_engine: Optional[str] = None,
    requires_approval: bool = False,
) -> GovernanceDecision:
    """
    Evaluate one task against the actor's profile limits. Fail-closed by default.

    Returns a GovernanceDecision naming the state the task must be written with:
      * ``dead_letter``        — hard deny (unknown role, forbidden classification,
                                 engine outside owned_engines)
      * ``awaiting_approval``  — frozen for a human (financial limit crossed,
                                 low confidence, explicit approval requested)
      * ``executing``          — inside every boundary, may proceed autonomously
    """
    cost = _require_money(estimated_financial_cost, "evaluate_gate.estimated_financial_cost")
    confidence = _require_confidence(confidence_score, "evaluate_gate.confidence_score")

    try:
        spec = get_role(role_id)
    except ValueError as exc:
        return GovernanceDecision(
            allowed=False,
            requires_human_approval=False,
            reason_code="unknown_role",
            reason=str(exc),
            state=WorkflowState.DEAD_LETTER,
            estimated_cost_usd=cost,
            limit_usd=None,
        )

    if data_classification not in DataClassification.ALL:
        return GovernanceDecision(
            allowed=False,
            requires_human_approval=False,
            reason_code="unknown_classification",
            reason=f"unknown data classification {data_classification!r} — fail closed",
            state=WorkflowState.DEAD_LETTER,
            estimated_cost_usd=cost,
            limit_usd=spec.financial_approval_limit_usd,
        )

    if not spec.can_read(data_classification):
        return GovernanceDecision(
            allowed=False,
            requires_human_approval=False,
            reason_code="classification_not_permitted",
            reason=(
                f"role {spec.role_id!r} may not touch {data_classification!r} data "
                f"(allowed: {list(spec.allowed_data_classifications)})"
            ),
            state=WorkflowState.DEAD_LETTER,
            estimated_cost_usd=cost,
            limit_usd=spec.financial_approval_limit_usd,
        )

    if target_engine is not None and not spec.owns_engine(target_engine):
        return GovernanceDecision(
            allowed=False,
            requires_human_approval=False,
            reason_code="access_denied",
            reason=(
                f"engine {target_engine!r} is not in role {spec.role_id!r} owned_engines "
                f"{list(spec.owned_engines)}"
            ),
            state=WorkflowState.DEAD_LETTER,
            estimated_cost_usd=cost,
            limit_usd=spec.financial_approval_limit_usd,
        )

    limit = spec.financial_approval_limit_usd

    # Financial boundary: cross the limit -> freeze for human validation.
    if limit is not None and cost > limit:
        return GovernanceDecision(
            allowed=True,
            requires_human_approval=True,
            reason_code="financial_limit_exceeded",
            reason=(
                f"estimated_financial_cost {cost:.2f} USD exceeds role {spec.role_id!r} "
                f"approval limit {limit:.2f} USD"
            ),
            state=WorkflowState.AWAITING_APPROVAL,
            estimated_cost_usd=cost,
            limit_usd=limit,
        )

    # Safety confidence boundary.
    if confidence < MIN_AUTONOMY_CONFIDENCE:
        return GovernanceDecision(
            allowed=True,
            requires_human_approval=True,
            reason_code="low_confidence",
            reason=(
                f"confidence_score {confidence:.2f} below autonomy threshold "
                f"{MIN_AUTONOMY_CONFIDENCE:.2f}"
            ),
            state=WorkflowState.AWAITING_APPROVAL,
            estimated_cost_usd=cost,
            limit_usd=limit,
        )

    if requires_approval:
        return GovernanceDecision(
            allowed=True,
            requires_human_approval=True,
            reason_code="approval_requested",
            reason="task was submitted with requires_approval=True",
            state=WorkflowState.AWAITING_APPROVAL,
            estimated_cost_usd=cost,
            limit_usd=limit,
        )

    return GovernanceDecision(
        allowed=True,
        requires_human_approval=False,
        reason_code="within_bounds",
        reason=f"task is inside every boundary for role {spec.role_id!r}",
        state=WorkflowState.EXECUTING,
        estimated_cost_usd=cost,
        limit_usd=limit,
    )


# ── durable records ────────────────────────────────────────────────────────


@dataclass
class WorkflowTaskRecord:
    """Row contract for the ``workflow_tasks`` table."""

    task_id: str
    correlation_id: str
    tenant_id: Optional[str]
    client_id: Optional[str]
    actor_id: str
    actor_role_id: str
    owning_role_id: str
    capability: str
    target_engine: Optional[str]
    state: str
    estimated_financial_cost: float
    financial_limit_usd: Optional[float]
    data_classification: str
    confidence_score: float
    reason_code: str
    reason: str
    created_at: str
    updated_at: str
    workflow_id: Optional[str] = None
    payload: Dict[str, Any] = field(default_factory=dict)
    error: Optional[Dict[str, Any]] = None
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_uuid4(self.task_id, "WorkflowTaskRecord.task_id")
        _require_non_empty_str(self.correlation_id, "WorkflowTaskRecord.correlation_id")
        _require_non_empty_str(self.actor_id, "WorkflowTaskRecord.actor_id")
        _require_non_empty_str(self.capability, "WorkflowTaskRecord.capability")
        if self.state not in WorkflowState.ALL:
            raise ValueError(
                f"WorkflowTaskRecord.state: must be one of {sorted(WorkflowState.ALL)}, got {self.state!r}"
            )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "workflow_id": self.workflow_id,
            "correlation_id": self.correlation_id,
            "tenant_id": self.tenant_id,
            "client_id": self.client_id,
            "actor_id": self.actor_id,
            "actor_role_id": self.actor_role_id,
            "owning_role_id": self.owning_role_id,
            "capability": self.capability,
            "target_engine": self.target_engine,
            "state": self.state,
            "estimated_financial_cost": self.estimated_financial_cost,
            "financial_limit_usd": self.financial_limit_usd,
            "data_classification": self.data_classification,
            "confidence_score": self.confidence_score,
            "reason_code": self.reason_code,
            "reason": self.reason,
            "payload": self.payload,
            "error": self.error,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "schema_version": self.schema_version,
        }

    @classmethod
    def from_row(cls, row: Dict[str, Any]) -> "WorkflowTaskRecord":
        return cls(
            task_id=row["task_id"],
            workflow_id=row.get("workflow_id"),
            correlation_id=row["correlation_id"],
            tenant_id=row.get("tenant_id"),
            client_id=row.get("client_id"),
            actor_id=row["actor_id"],
            actor_role_id=row["actor_role_id"],
            owning_role_id=row["owning_role_id"],
            capability=row["capability"],
            target_engine=row.get("target_engine"),
            state=row["state"],
            estimated_financial_cost=float(row.get("estimated_financial_cost") or 0.0),
            financial_limit_usd=(
                None
                if row.get("financial_limit_usd") is None
                else float(row["financial_limit_usd"])
            ),
            data_classification=row["data_classification"],
            confidence_score=float(
                row.get("confidence_score") if row.get("confidence_score") is not None else 1.0
            ),
            reason_code=row.get("reason_code") or "",
            reason=row.get("reason") or "",
            payload=row.get("payload") or {},
            error=row.get("error"),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            schema_version=row.get("schema_version", SCHEMA_VERSION),
        )


@dataclass
class AuditEventRecord:
    """Row contract for the append-only ``audit_events`` ledger."""

    event_id: str
    occurred_at: str
    correlation_id: str
    actor_id: str
    actor_role_id: str
    event_type: str
    decision: str
    reason_code: str
    reason: str
    task_id: Optional[str] = None
    workflow_id: Optional[str] = None
    from_state: Optional[str] = None
    to_state: Optional[str] = None
    payload: Dict[str, Any] = field(default_factory=dict)
    prev_hash: str = ""
    record_hash: str = ""

    def __post_init__(self) -> None:
        _require_uuid4(self.event_id, "AuditEventRecord.event_id")
        _require_non_empty_str(self.event_type, "AuditEventRecord.event_type")
        if self.decision not in {"allowed", "held", "denied"}:
            raise ValueError(
                f"AuditEventRecord.decision: must be allowed|held|denied, got {self.decision!r}"
            )

    def signing_payload(self) -> Dict[str, Any]:
        d = {
            "event_id": self.event_id,
            "occurred_at": self.occurred_at,
            "correlation_id": self.correlation_id,
            "actor_id": self.actor_id,
            "actor_role_id": self.actor_role_id,
            "event_type": self.event_type,
            "decision": self.decision,
            "reason_code": self.reason_code,
            "reason": self.reason,
            "task_id": self.task_id,
            "workflow_id": self.workflow_id,
            "from_state": self.from_state,
            "to_state": self.to_state,
            "payload": self.payload,
            "prev_hash": self.prev_hash,
        }
        return d

    def compute_hash(self) -> str:
        return _sha256(self.signing_payload())

    def to_dict(self) -> Dict[str, Any]:
        d = self.signing_payload()
        d["record_hash"] = self.record_hash
        return d


# ── governed workflow manager ──────────────────────────────────────────────


class GovernedWorkflowManager:
    """
    Fail-closed workflow manager for the enterprise control plane.

    Every state write goes through :meth:`_commit_state`, which re-evaluates the
    task against the actor's profile limits *before* touching the database. A task
    that crosses a risk boundary is never dropped on the floor and never crashes
    the engine: it is frozen in ``awaiting_approval`` (or isolated in
    ``dead_letter`` for hard denies) with a durable audit trail.
    """

    def __init__(self, store: Optional[Store] = None, db_path: Optional[str] = None) -> None:
        self.store = store or Store(db_path or "control_plane/workflow.db")

    # ── submit ─────────────────────────────────────────────────────────────

    def submit(
        self, request: TaskRequest, *, target_engine: Optional[str] = None
    ) -> WorkflowTaskRecord:
        """
        Admit a governed task request.

        Never raises for a governance violation: violations are trapped in the
        database (dead_letter / awaiting_approval) and audited, so a bad proposal
        cannot take the engine down.
        """
        engine = normalize_engine(target_engine) if target_engine else request.target_engine
        if engine:
            engine = normalize_engine(engine)

        actor_role_id = resolve_actor_role(request.requesting_actor, request.owning_role_id)
        now = _now_iso()

        decision = evaluate_gate(
            actor_role_id or "<unresolved>",
            estimated_financial_cost=request.estimated_financial_cost,
            data_classification=request.requested_data_classification,
            confidence_score=request.confidence_score,
            target_engine=engine,
            requires_approval=request.requires_approval,
        )

        limit = decision.limit_usd
        record = WorkflowTaskRecord(
            task_id=str(uuid.uuid4()),
            workflow_id=None,
            correlation_id=request.correlation.correlation_id,
            tenant_id=request.tenant_id or request.correlation.tenant_id,
            client_id=request.client_id or request.correlation.client_id,
            actor_id=request.requesting_actor,
            actor_role_id=actor_role_id or "<unresolved>",
            owning_role_id=request.owning_role_id,
            capability=request.capability,
            target_engine=engine,
            state=WorkflowState.PROPOSED,
            estimated_financial_cost=request.estimated_financial_cost,
            financial_limit_usd=limit,
            data_classification=request.requested_data_classification,
            confidence_score=request.confidence_score,
            reason_code=decision.reason_code,
            reason=decision.reason,
            created_at=now,
            updated_at=now,
            payload=request.input_payload,
        )
        self.store.insert_workflow_task(record.to_dict())

        self._append_audit(
            record,
            actor_id=request.requesting_actor,
            actor_role_id=record.actor_role_id,
            event_type="task_proposed",
            decision="denied"
            if not decision.allowed
            else ("held" if decision.requires_human_approval else "allowed"),
            reason_code=decision.reason_code,
            reason=decision.reason,
            from_state=None,
            to_state=WorkflowState.PROPOSED,
        )

        # proposed -> validated (structural contract shapes already validated by TaskRequest)
        if decision.allowed:
            record = self._commit_state(record, WorkflowState.VALIDATED, request.requesting_actor)
            # validated -> gate outcome
            record = self._commit_state(
                record,
                decision.state,
                request.requesting_actor,
                reason_code=decision.reason_code,
                reason=decision.reason,
            )
        else:
            record = self._commit_state(
                record,
                WorkflowState.FAILED,
                request.requesting_actor,
                reason_code=decision.reason_code,
                reason=decision.reason,
                error={"code": decision.reason_code, "message": decision.reason},
            )
            # Isolated: the spec routes failed work to the dead-letter queue.
            record = self._commit_state(
                record,
                WorkflowState.DEAD_LETTER,
                "system",
                reason_code=decision.reason_code,
                reason=decision.reason,
                error={"code": decision.reason_code, "message": decision.reason},
            )
        return record

    # ── human approval ─────────────────────────────────────────────────────

    def approve(
        self,
        task_id: str,
        approver_id: str,
        *,
        note: str = "",
    ) -> WorkflowTaskRecord:
        """
        Commit a human validation token for a frozen task.

        Fail-closed checks:
          * task must be in ``awaiting_approval``
          * no self-approval (segregation of duties)
          * the approver's own limit must cover the task's estimated cost
        """
        record = self._load(task_id)
        if record.state != WorkflowState.AWAITING_APPROVAL:
            raise GovernanceStateError(
                f"approve: task {task_id!r} is {record.state!r}, not awaiting_approval"
            )
        if approver_id == record.actor_id:
            raise GovernanceStateError(
                f"approve: segregation of duties — approver {approver_id!r} cannot approve their own task"
            )

        approver_role_id = resolve_actor_role(approver_id)
        if not approver_role_id:
            raise GovernanceStateError(
                f"approve: unknown approver {approver_id!r} — cannot validate"
            )

        approver_limit = get_role(approver_role_id).financial_approval_limit_usd
        if approver_limit is not None and record.estimated_financial_cost > approver_limit:
            raise GovernanceStateError(
                f"approve: estimated_financial_cost {record.estimated_financial_cost:.2f} USD exceeds "
                f"approver {approver_role_id!r} limit {approver_limit:.2f} USD — escalate to SAMI"
            )

        record = self._commit_state(
            record,
            WorkflowState.APPROVED,
            approver_id,
            reason_code="human_approved",
            reason=note or f"approved by {approver_id} ({approver_role_id})",
            actor_role_id=approver_role_id,
        )
        return self._commit_state(
            record,
            WorkflowState.EXECUTING,
            approver_id,
            reason_code="human_approved",
            reason=note or f"released for execution by {approver_id}",
            actor_role_id=approver_role_id,
            human_approved=True,
        )

    def reject(self, task_id: str, approver_id: str, *, note: str = "") -> WorkflowTaskRecord:
        """Human rejects a frozen task -> cancelled."""
        record = self._load(task_id)
        if record.state != WorkflowState.AWAITING_APPROVAL:
            raise GovernanceStateError(
                f"reject: task {task_id!r} is {record.state!r}, not awaiting_approval"
            )
        return self._commit_state(
            record,
            WorkflowState.CANCELLED,
            approver_id,
            reason_code="human_rejected",
            reason=note or f"rejected by {approver_id}",
            actor_role_id=resolve_actor_role(approver_id) or "<unresolved>",
        )

    # ── completion ─────────────────────────────────────────────────────────

    def complete(
        self,
        task_id: str,
        to_state: str,
        actor_id: str = "system",
        *,
        output_payload: Optional[Dict[str, Any]] = None,
        error: Optional[Dict[str, Any]] = None,
    ) -> WorkflowTaskRecord:
        """Move an executing task to ``succeeded`` or ``failed``."""
        if to_state not in (WorkflowState.SUCCEEDED, WorkflowState.FAILED):
            raise GovernanceStateError(
                f"complete: terminal state must be succeeded|failed, got {to_state!r}"
            )
        record = self._load(task_id)
        payload = dict(record.payload)
        if output_payload is not None:
            payload["output"] = output_payload
        record.payload = payload
        return self._commit_state(
            record,
            to_state,
            actor_id,
            reason_code="engine_succeeded"
            if to_state == WorkflowState.SUCCEEDED
            else "engine_failed",
            reason=f"task {to_state}",
            error=error,
        )

    # ── reads ──────────────────────────────────────────────────────────────

    def get_task(self, task_id: str) -> Optional[WorkflowTaskRecord]:
        row = self.store.get_workflow_task(task_id)
        return WorkflowTaskRecord.from_row(row) if row else None

    def list_tasks(
        self, *, state: Optional[str] = None, limit: int = 100
    ) -> List[WorkflowTaskRecord]:
        return [
            WorkflowTaskRecord.from_row(r)
            for r in self.store.list_workflow_tasks(state=state, limit=limit)
        ]

    def audit_trail(self, task_id: Optional[str] = None, limit: int = 200) -> List[Dict[str, Any]]:
        return self.store.list_audit_events(task_id=task_id, limit=limit)

    def verify_audit_chain(self) -> bool:
        return self.store.verify_audit_chain()

    # ── internals ──────────────────────────────────────────────────────────

    def _load(self, task_id: str) -> WorkflowTaskRecord:
        row = self.store.get_workflow_task(task_id)
        if row is None:
            raise GovernanceStateError(f"task {task_id!r} not found")
        return WorkflowTaskRecord.from_row(row)

    def _commit_state(
        self,
        record: WorkflowTaskRecord,
        to_state: str,
        actor_id: str,
        *,
        reason_code: str = "",
        reason: str = "",
        error: Optional[Dict[str, Any]] = None,
        actor_role_id: Optional[str] = None,
        human_approved: bool = False,
    ) -> WorkflowTaskRecord:
        """
        Single choke point for state writes.

        Re-checks the transition against the state machine and re-evaluates the
        financial boundary *before* the row is written, so a task cannot slip past
        its limit on a later transition.
        """
        if not is_valid_transition(record.state, to_state):
            raise GovernanceStateError(
                f"invalid transition {record.state!r} -> {to_state!r} for task {record.task_id!r}"
            )

        # Fail-closed re-evaluation on any transition that leaves the frozen queue.
        # A committed human validation token is the one thing that overrides the
        # autonomous boundary: the authorized human now owns the risk.
        if to_state == WorkflowState.EXECUTING and not human_approved:
            decision = evaluate_gate(
                record.actor_role_id,
                estimated_financial_cost=record.estimated_financial_cost,
                data_classification=record.data_classification,
                confidence_score=record.confidence_score,
                target_engine=record.target_engine,
            )
            if decision.requires_human_approval:
                to_state = WorkflowState.AWAITING_APPROVAL
                reason_code = decision.reason_code
                reason = decision.reason

        from_state = record.state
        record.state = to_state
        record.updated_at = _now_iso()
        if reason_code:
            record.reason_code = reason_code
        if reason:
            record.reason = reason
        if error is not None:
            record.error = error

        self.store.update_workflow_task_state(
            record.task_id,
            record.state,
            updated_at=record.updated_at,
            reason_code=record.reason_code,
            reason=record.reason,
            payload=record.payload,
            error=record.error,
        )

        self._append_audit(
            record,
            actor_id=actor_id,
            actor_role_id=actor_role_id or record.actor_role_id,
            event_type=f"task_{to_state}",
            decision=(
                "denied"
                if to_state in (WorkflowState.DEAD_LETTER, WorkflowState.FAILED)
                else ("held" if to_state == WorkflowState.AWAITING_APPROVAL else "allowed")
            ),
            reason_code=reason_code,
            reason=reason,
            from_state=from_state,
            to_state=to_state,
        )
        return record

    def _append_audit(
        self,
        record: WorkflowTaskRecord,
        *,
        actor_id: str,
        actor_role_id: str,
        event_type: str,
        decision: str,
        reason_code: str,
        reason: str,
        from_state: Optional[str],
        to_state: Optional[str],
    ) -> AuditEventRecord:
        prev_hash = self.store.get_last_audit_hash()
        event = AuditEventRecord(
            event_id=str(uuid.uuid4()),
            occurred_at=_now_iso(),
            correlation_id=record.correlation_id,
            actor_id=actor_id,
            actor_role_id=actor_role_id,
            event_type=event_type,
            decision=decision,
            reason_code=reason_code,
            reason=reason,
            task_id=record.task_id,
            workflow_id=record.workflow_id,
            from_state=from_state,
            to_state=to_state,
            payload={
                "capability": record.capability,
                "target_engine": record.target_engine,
                "estimated_financial_cost": record.estimated_financial_cost,
                "financial_limit_usd": record.financial_limit_usd,
                "data_classification": record.data_classification,
                "confidence_score": record.confidence_score,
            },
            prev_hash=prev_hash,
        )
        event.record_hash = event.compute_hash()
        self.store.append_audit_event(event.to_dict())
        return event


__all__ = [
    "SCHEMA_VERSION",
    "MIN_AUTONOMY_CONFIDENCE",
    "AccessDeniedError",
    "GovernanceStateError",
    "RoleCatalogUnavailableError",
    "RoleSpec",
    "ORGANIZATION_CATALOG",
    "ENGINE_ALIASES",
    "ACTOR_ALIASES",
    "YAML_ROLE_ALIASES",
    "FINANCIAL_LIMIT_OVERRIDES",
    "UNLIMITED_FINANCIAL_ROLES",
    "ACCEPTED_FINANCIAL_DRIFT_ROLES",
    "normalize_engine",
    "get_role",
    "resolve_actor_role",
    "detect_catalog_drift",
    "CorrelationContext",
    "TaskRequest",
    "TaskResult",
    "GovernanceDecision",
    "evaluate_gate",
    "WorkflowTaskRecord",
    "AuditEventRecord",
    "GovernedWorkflowManager",
]
