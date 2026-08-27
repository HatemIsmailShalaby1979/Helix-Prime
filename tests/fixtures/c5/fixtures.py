"""Deterministic synthetic fixtures for the C5 contact-centre vertical slice.

Every fixture is clearly labeled as SAMPLE / SYNTHETIC data.
Do not use these for production claims; this is C5 Codex milestone proof only.
"""
from __future__ import annotations

import datetime
from typing import Any, Dict

# Common
TENANT_ID = "tenant_demo_001"
CLIENT_ID = "client_alpha"
ACTOR_SUBY = "suby"
ACTOR_SAMI = "sami"
ACTOR_PHILI = "phili"
ACTOR_WILI = "wili"
ACTOR_COMPLIANCE = "compliance_user"
ACTOR_SALES = "sales_user"

# Step 1: WFM interval/contact data (synthetic)
WFM_INPUT: Dict[str, Any] = {
    "contacts": 200,  # 200 calls in the interval
    "interval_minutes": 60,  # 1-hour interval
    "aht_seconds": 480,  # 8 minutes average handle time
    "service_level_target": 0.80,  # 80% answered within 20s (Erlang C uses this)
    "average_calls_per_period": 17,
    "is_sample": True,
    "data_classification": "internal",
}

# Step 2: RTA schedule/actual data (synthetic)
RTA_INPUT: Dict[str, Any] = {
    "schedule": {
        "agent_id": ["A1", "A2", "A3"],
        "scheduled_min": [480, 480, 480],
        "date": ["2026-08-27", "2026-08-27", "2026-08-27"],
        "hour": [9, 9, 9],
        "scheduled_hours": [8.0, 8.0, 8.0],
    },
    "actual": {
        "agent_id": ["A1", "A2", "A3"],
        "logged_min": [470, 460, 480],
        "productive_min": [460, 450, 470],
        "date": ["2026-08-27", "2026-08-27", "2026-08-27"],
        "hour": [9, 9, 9],
        "actual_hours": [7.83, 7.67, 8.0],
    },
    "is_sample": True,
    "data_classification": "internal",
}

# Step 5: HR/Personnel (synthetic)
PERSONNEL_INPUT: Dict[str, Any] = {
    "candidate": {
        "name": "Alice Smith",
        "role": "Agent",
        "skills": ["Customer Service", "Sales"],
    },
    "workforce": {
        "headcount": 420,
        "open_positions": 5,
    },
    "is_sample": True,
    "data_classification": "personnel_sensitive",
}

# Step 6: L&D competency gap (synthetic, derived from WFM + OPS)
LD_INPUT: Dict[str, Any] = {
    "competency_gap": "customer_service_adherence",
    "recommended_training": "Adherence Coaching 101 (synthetic)",
    "is_sample": True,
    "data_classification": "internal",
}

# Step 7: CX churn impact (synthetic)
CX_INPUT: Dict[str, Any] = {
    "customers": [
        {"csat": 0.82, "sla": 0.88, "fcr": 0.85, "aht": 0.30},
        {"csat": 0.75, "sla": 0.82, "fcr": 0.80, "aht": 0.32},
        {"csat": 0.90, "sla": 0.95, "fcr": 0.92, "aht": 0.28},
    ],
    "is_sample": True,
    "data_classification": "client_confidential",
}

# Step 8: CRM impact (synthetic)
CRM_INPUT: Dict[str, Any] = {
    "client": {"name": "Client Alpha", "id": "client_alpha"},
    "deal": {"id": "deal_alpha_001", "value": 50000, "stage": "proposal"},
    "is_sample": True,
    "data_classification": "client_confidential",
}

# OPS recommendation (derived; deterministic)
OPS_RECOMMENDATION: Dict[str, Any] = {
    "summary": "Service level 0.78 below 0.80 target. Recommend +5 agents (Erlang C) and adherence coaching.",
    "rationale": "Derived from WFM optimal_agents and RTA adherence; deterministic.",
    "source": "calculated",
    "is_sample": True,
    "data_classification": "internal",
}

# SAMI summary (derived)
SAMI_SUMMARY: Dict[str, Any] = {
    "executive_summary": "Contact-centre vertical slice complete. WFM staffing gap +5; RTA adherence within tolerance; OPS recommendation requires Compliance approval; HR/L&D and CX/CRM impact noted. All steps synthetic/sample data.",
    "decisions": [
        "WFM: +5 agents recommended (Erlang C calculated)",
        "RTA: adherence within tolerance (calculated)",
        "OPS: recommendation generated; Compliance approval required",
        "HR/Personnel: 5 open positions (PipelineManager calculated)",
        "L&D: adherence coaching recommended (derived)",
        "CX: 1 of 3 customers at elevated risk (RiskScorer calculated)",
        "CRM: 1 deal in proposal stage ($50k) (SalesPipeline calculated)",
    ],
    "kpi_summary": {
        "service_level_target": 0.80,
        "adherence_overall": 0.96,
        "open_positions": 5,
        "high_risk_customers": 1,
        "active_deals": 1,
    },
    "is_sample": True,
    "data_classification": "internal",
}


def get_sample_inputs():
    """Return all C5 sample inputs as a dict keyed by step."""
    return {
        "wfm": WFM_INPUT,
        "rta": RTA_INPUT,
        "personnel": PERSONNEL_INPUT,
        "ld": LD_INPUT,
        "cx": CX_INPUT,
        "crm": CRM_INPUT,
    }


def now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")
