"""Pilot scope, policies, and the three distinguished data modes (Prompt 10).

The pilot explicitly separates:
* historical_consented  — real customer data already consented for the pilot
* simulated_realistic  — synthetic data that mimics production shape
* live_customer        — live production data; NOT activated by the pilot package
"""
from __future__ import annotations

from dataclasses import dataclass

HISTORICAL_CONSENTED = "historical_consented"
SIMULATED_REALISTIC = "simulated_realistic"
LIVE_CUSTOMER = "live_customer"

DATA_MODE_DISTINCTION = (
    (HISTORICAL_CONSENTED, "Real customer data previously consented for the pilot; tenant-scoped, classified."),
    (SIMULATED_REALISTIC, "Synthetic data mirroring production shape; used for dry-runs and demos."),
    (LIVE_CUSTOMER, "Live production customer data. NOT activated by the pilot package; requires separate real design-partner approval."),
)


@dataclass(frozen=True)
class DataClassificationPolicy:
    levels: tuple = ("public", "internal", "client_confidential", "restricted")
    default: str = "client_confidential"
    note: str = "Pilot data is client_confidential; live customer data is never activated here."


@dataclass(frozen=True)
class MinimumDataPolicy:
    enabled: bool = True
    collected_fields: tuple = ("account_id", "health_state", "risk_factors", "recommended_action")
    excluded_fields: tuple = ("raw_conversation_transcripts", "payment_instruments", "government_ids")


@dataclass(frozen=True)
class TenantIsolationConfig:
    enabled: bool = True
    enforcement: str = "governed_memory_tenant_scope"


@dataclass(frozen=True)
class ReadOnlyConnectorConfig:
    mode: str = "fake"
    writes_enabled: bool = False
    note: str = "Connectors are fake/credential-neutral; request_write is disabled by design."


@dataclass(frozen=True)
class RetentionDeletionPolicy:
    retention_days: int = 90
    soft_delete: bool = True
    deletion_requires_approval: bool = True


@dataclass(frozen=True)
class SuccessMetric:
    key: str
    definition: str
    unit: str


@dataclass(frozen=True)
class ReviewChecklistItem:
    item: str
    required: bool = True


@dataclass(frozen=True)
class PilotScope:
    name: str
    objectives: tuple
    data_classification: DataClassificationPolicy
    minimum_data: MinimumDataPolicy
    tenant_isolation: TenantIsolationConfig
    read_only_connectors: ReadOnlyConnectorConfig
    retention: RetentionDeletionPolicy
    success_metrics: tuple
    review_checklist: tuple
    data_mode_distinction: tuple = DATA_MODE_DISTINCTION


def default_scope() -> PilotScope:
    return PilotScope(
        name="Helix Codex Design-Partner Pilot",
        objectives=(
            "Validate governed, read-only call-centre + customer-success assistance on consented/synthetic data.",
            "Prove every recommendation carries evidence and every committal action has an owner + approval state.",
            "Confirm no live connectors, cloud services, or external writes are activated automatically.",
        ),
        data_classification=DataClassificationPolicy(),
        minimum_data=MinimumDataPolicy(),
        tenant_isolation=TenantIsolationConfig(),
        read_only_connectors=ReadOnlyConnectorConfig(),
        retention=RetentionDeletionPolicy(),
        success_metrics=(
            SuccessMetric("response_time_reduction", "Baseline minus realized response time", "minutes"),
            SuccessMetric("escalation_accuracy", "Share of escalations that matched a genuine risk state", "ratio"),
            SuccessMetric("unresolved_risk_age", "Age of the oldest open risk factor", "days"),
            SuccessMetric("customer_health_visibility", "Share of accounts with a confident diagnosis", "ratio"),
            SuccessMetric("missed_follow_ups", "Recommended actions not approved/executed", "count"),
            SuccessMetric("recommendation_acceptance_rate", "Approved / total recommendations", "ratio"),
            SuccessMetric("correction_rate", "Corrections / total records", "ratio"),
            SuccessMetric("operator_time_saved", "Estimated operator minutes saved", "minutes"),
        ),
        review_checklist=(
            ReviewChecklistItem("Customer consent recorded and validated"),
            ReviewChecklistItem("Only consented/synthetic data in use (no live customer data)"),
            ReviewChecklistItem("Connectors read-only; no external writes"),
            ReviewChecklistItem("Every recommendation has evidence references"),
            ReviewChecklistItem("Every committal action has an owner and approval state"),
            ReviewChecklistItem("Every outcome recorded in governed memory"),
            ReviewChecklistItem("Tenant isolation verified"),
            ReviewChecklistItem("Retention & deletion policy applied"),
            ReviewChecklistItem("Incident & rollback procedure documented and tested"),
            ReviewChecklistItem("Evidence pack generated and reviewed"),
        ),
    )
