"""
Functional GM activation — Helix Codex OS C6.

The organization catalog already *describes* nine roles. Describing a role and
activating it are different things: a described role is a document, an activated
role is one whose validation properties are bound to the runtime RoleSpec
registry and enforced on every call.

This module performs the binding, and refuses to activate anything it cannot
verify:

* the role must exist in :data:`~control_plane.governance.ORGANIZATION_CATALOG`
  (runtime RoleSpec — financial limits, owned engines, classifications, KPIs);
* the role must exist in ``organization/role-catalog.yaml`` (capabilities,
  tools, peer calls, segregation of duties);
* every capability the GM claims must be present in the YAML catalog;
* every engine the GM touches must be in the RoleSpec's ``owned_engines``,
  unless the RoleSpec is ``oversight_only`` (compliance proposes, never
  executes);
* every KPI the activation reports must be one the RoleSpec declares.

A GM that fails any of these is reported as ``blocked`` with the reason. It is
never silently activated with reduced powers — a half-activated GM is worse
than an absent one, because it looks like it is enforcing something.
"""
from __future__ import annotations

import pathlib
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from control_plane.governance import ORGANIZATION_CATALOG, RoleSpec, normalize_engine

DEFAULT_CATALOG_PATH = "organization/role-catalog.yaml"

SCHEMA_VERSION = "1.0"

#: Roles that are part of the C6 activation track. SAMI is the C1 baseline and
#: ops_gm was activated with the C5 vertical slice, so neither is "remaining".
C6_ROLE_IDS: Tuple[str, ...] = (
    "compliance_quality_gm",
    "fraud_revenue_gm",
    "hr_personnel_gm",
    "ld_gm",
    "sales_gm",
    "marketing_gm",
    "ict_gm",
)

# The YAML catalog predates the runtime RoleSpec rename. Keep the alias
# explicit and auditable rather than silently treating the two IDs as equal.
YAML_ROLE_ALIASES = {"fraud_revenue_gm": "fraud_gm"}


@dataclass(frozen=True)
class GMActivation:
    """One GM's declared operating envelope."""

    role_id: str
    agent_name: str
    mission: str
    owned_capabilities: Tuple[str, ...]
    engines_used: Tuple[str, ...]
    kpis_reported: Tuple[str, ...]
    validation_properties: Tuple[str, ...] = ()
    oversight_only: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "role_id": self.role_id,
            "agent_name": self.agent_name,
            "mission": self.mission,
            "owned_capabilities": list(self.owned_capabilities),
            "engines_used": list(self.engines_used),
            "kpis_reported": list(self.kpis_reported),
            "validation_properties": list(self.validation_properties),
            "oversight_only": self.oversight_only,
            "schema_version": SCHEMA_VERSION,
        }


#: The declared envelope for each remaining GM. This is the C6 activation
#: manifest — edit it here, and every check below re-derives from it.
ACTIVATIONS: Dict[str, GMActivation] = {
    "compliance_quality_gm": GMActivation(
        role_id="compliance_quality_gm",
        agent_name="ANDY",
        mission=(
            "Runs QA batch tests, generates evidence archives, and controls "
            "transaction overrides."
        ),
        owned_capabilities=("policy_enforcement", "qa_sampling", "evidence_pack"),
        engines_used=(),  # oversight only
        kpis_reported=("quality_score", "compliance_drift"),
        validation_properties=(
            "qa_batch_sampling",
            "evidence_archive_export",
            "transaction_override_control",
            "append_only_ledger_integrity",
        ),
        oversight_only=True,
    ),
    "fraud_revenue_gm": GMActivation(
        role_id="fraud_revenue_gm",
        agent_name="NONO",
        mission="Scans workflows for anomalies and monitors financial leakage boundaries.",
        owned_capabilities=("anomaly_detection", "revenue_assurance", "leakage_analysis"),
        engines_used=("crm", "b2b"),
        kpis_reported=("leakage", "anomaly_delta"),
        validation_properties=(
            "anomaly_scan",
            "financial_leakage_boundary",
            "workflow_deviation_review",
        ),
    ),
    "hr_personnel_gm": GMActivation(
        role_id="hr_personnel_gm",
        agent_name="PHILI",
        mission=(
            "Handles resource requests, tracks candidate pipelines, and triggers "
            "employee onboarding paths."
        ),
        owned_capabilities=("talent_acquisition", "workforce_planning", "hiring_pipeline"),
        engines_used=("personnel", "wfm"),
        kpis_reported=("turnover_rate", "time_to_hire"),
        validation_properties=(
            "resource_requisition",
            "candidate_pipeline_tracking",
            "onboarding_trigger",
        ),
    ),
    "ld_gm": GMActivation(
        role_id="ld_gm",
        agent_name="WILI",
        mission="Monitors workforce skill profiles and coordinates targeted training pipelines.",
        owned_capabilities=("competency_analysis", "training_design"),
        engines_used=("wfm",),
        kpis_reported=("competency_score", "time_to_competency"),
        validation_properties=(
            "skill_profile_monitoring",
            "training_pipeline_coordination",
            "competency_gap_ingest",
        ),
    ),
    "sales_gm": GMActivation(
        role_id="sales_gm",
        agent_name="LIZA",
        mission="Tracks active opportunities, manages client proposals, and audits pipeline health.",
        owned_capabilities=("sales_pipeline", "crm_operations", "proposal_generation"),
        engines_used=("crm", "b2b"),
        kpis_reported=("pipeline_value", "win_rate"),
        validation_properties=(
            "opportunity_tracking",
            "proposal_management",
            "pipeline_health_audit",
        ),
    ),
    "marketing_gm": GMActivation(
        role_id="marketing_gm",
        agent_name="MAYA",
        mission="Audits demand-generation signals and manages campaign and positioning inputs.",
        owned_capabilities=("demand_generation", "market_intelligence", "campaign_management"),
        engines_used=("crm",),
        kpis_reported=("cac", "lead_volume"),
        validation_properties=(
            "demand_signal_audit",
            "campaign_signal_tracking",
        ),
    ),
    "ict_gm": GMActivation(
        role_id="ict_gm",
        agent_name="TOMY",
        mission="Monitors engine performance profiles and isolates unexpected system execution faults.",
        owned_capabilities=("platform_ops", "integration_management", "reliability"),
        engines_used=("control_plane",),
        kpis_reported=("engine_latency", "model_timeout"),
        validation_properties=(
            "engine_performance_profile",
            "execution_fault_isolation",
            "platform_health_monitoring",
        ),
    ),
}


@dataclass
class ActivationResult:
    """Outcome of validating one GM activation against the registries."""

    role_id: str
    activated: bool
    spec: Optional[RoleSpec] = None
    activation: Optional[GMActivation] = None
    problems: List[str] = field(default_factory=list)
    yaml_status: Optional[str] = None

    @property
    def status(self) -> str:
        if self.activated:
            return "active"
        return "blocked"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "role_id": self.role_id,
            "status": self.status,
            "activated": self.activated,
            "problems": list(self.problems),
            "yaml_implementation_status": self.yaml_status,
            "spec": self.spec.to_dict() if self.spec else None,
            "activation": self.activation.to_dict() if self.activation else None,
        }


def _load_yaml_catalog(catalog_path: str = DEFAULT_CATALOG_PATH):
    try:
        from organization.role_catalog import load_role_catalog

        return load_role_catalog(catalog_path)
    except Exception:
        return None


def validate_activation(
    role_id: str,
    activation: GMActivation,
    *,
    yaml_catalog: Optional[Dict[str, Any]] = None,
) -> ActivationResult:
    """
    Check one GM activation against the runtime RoleSpec and the YAML catalog.

    Returns an :class:`ActivationResult`. Nothing here raises: a blocked GM is
    data, not an exception, so the whole fleet can be reported in one pass.
    """
    problems: List[str] = []

    if role_id not in ORGANIZATION_CATALOG:
        return ActivationResult(
            role_id=role_id,
            activated=False,
            activation=activation,
            problems=[f"role {role_id!r} is absent from the runtime ORGANIZATION_CATALOG"],
        )
    spec: RoleSpec = ORGANIZATION_CATALOG[role_id]

    yaml_status: Optional[str] = None
    if yaml_catalog:
        yaml_role_id = YAML_ROLE_ALIASES.get(role_id, role_id)
        yaml_role = (yaml_catalog.get("roles_by_id") or {}).get(yaml_role_id)
        if yaml_role is None:
            problems.append(
                f"role {role_id!r} (YAML id {yaml_role_id!r}) is absent from organization/role-catalog.yaml"
            )
        else:
            yaml_status = yaml_role.get("implementation_status")
            yaml_caps = set(yaml_role.get("owned_capabilities") or [])
            for capability in activation.owned_capabilities:
                if capability not in yaml_caps:
                    problems.append(
                        f"capability {capability!r} is not in the YAML catalog for {role_id!r}"
                    )
    else:
        problems.append(
            "organization/role-catalog.yaml could not be loaded — activation unverified"
        )

    # Engine ownership. Oversight-only roles own no engines and must claim none.
    if activation.oversight_only and not spec.oversight_only:
        problems.append(f"activation declares oversight_only but RoleSpec for {role_id!r} does not")
    if not spec.oversight_only:
        for engine in activation.engines_used:
            if not spec.owns_engine(engine):
                problems.append(
                    f"engine {normalize_engine(engine)!r} is not owned by {role_id!r} "
                    f"(owned: {list(spec.owned_engines)})"
                )
    elif activation.engines_used:
        problems.append(
            f"{role_id!r} is oversight_only and must not touch engines directly "
            f"(claimed: {list(activation.engines_used)})"
        )

    # KPI declarations must match the RoleSpec.
    for kpi in activation.kpis_reported:
        if kpi not in spec.kpis:
            problems.append(
                f"KPI {kpi!r} is not declared by RoleSpec {role_id!r} (declared: {list(spec.kpis)})"
            )

    if not activation.validation_properties:
        problems.append("activation declares no validation properties — nothing to enforce")

    return ActivationResult(
        role_id=role_id,
        activated=not problems,
        spec=spec,
        activation=activation,
        problems=problems,
        yaml_status=yaml_status,
    )


def activate_all(catalog_path: str = DEFAULT_CATALOG_PATH) -> Dict[str, ActivationResult]:
    """Validate every C6 GM activation. Returns role_id -> ActivationResult."""
    yaml_catalog = _load_yaml_catalog(catalog_path)
    return {
        role_id: validate_activation(role_id, activation, yaml_catalog=yaml_catalog)
        for role_id, activation in ACTIVATIONS.items()
    }


def activation_report(catalog_path: str = DEFAULT_CATALOG_PATH) -> Dict[str, Any]:
    """Machine-readable report for CI, the cockpit and the evidence pack."""
    results = activate_all(catalog_path)
    active = sorted(r for r, res in results.items() if res.activated)
    blocked = sorted(r for r, res in results.items() if not res.activated)
    return {
        "schema_version": SCHEMA_VERSION,
        "catalog_path": catalog_path,
        "total": len(results),
        "active": active,
        "blocked": blocked,
        "fully_activated": not blocked,
        "results": {role_id: res.to_dict() for role_id, res in sorted(results.items())},
    }


def active_engines() -> Dict[str, Tuple[str, ...]]:
    """Engine -> GMs that may touch it, derived from validated activations."""
    mapping: Dict[str, List[str]] = {}
    for role_id, activation in ACTIVATIONS.items():
        for engine in activation.engines_used:
            mapping.setdefault(normalize_engine(engine), []).append(role_id)
    return {engine: tuple(sorted(roles)) for engine, roles in sorted(mapping.items())}


def main() -> int:
    report = activation_report()
    print(f"GM activation — {len(report['active'])}/{report['total']} active")
    for role_id, res in sorted(
        (r, res) for r, res in ((k, v) for k, v in report["results"].items())
    ):
        pass
    for role_id in sorted(ACTIVATIONS):
        result = activate_all()[role_id]
        marker = "ACTIVE " if result.activated else "BLOCKED"
        print(f"  {marker} {role_id}")
        for problem in result.problems:
            print(f"          - {problem}")
    return 0 if report["fully_activated"] else 1


__all__ = [
    "ACTIVATIONS",
    "C6_ROLE_IDS",
    "DEFAULT_CATALOG_PATH",
    "SCHEMA_VERSION",
    "ActivationResult",
    "GMActivation",
    "activate_all",
    "activation_report",
    "active_engines",
    "validate_activation",
]

if __name__ == "__main__":
    raise SystemExit(main())
