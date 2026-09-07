"""
Concrete engine adapters — Helix Codex OS C4.

Six business engines, one interface. Each class extends
:class:`engines.base_adapter.EngineAdapter`, accepts an immutable
:class:`~contracts.task.TaskRequest`, and returns a strict
:class:`~contracts.task.TaskResult` plus an explicit computation-evidence dict.

Every adapter follows the same shape:

1. ``validate``  — reject a payload that cannot produce a trustworthy number.
2. ``compute``   — call the real engine module under ``engines/<id>/src/`` and
   normalise its output. No engine logic is reimplemented here.
3. ``baseline_payload`` — the bundled demo dataset, reachable only when
   ``sample_data_mode`` is True.

The baseline/live split is the point of the ``sample_data_mode`` toggle: the
demo dataset is declared as data, not smuggled in through a code path, so a live
run physically cannot fall back to it.
"""
from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Tuple

from engines.base_adapter import EngineAdapter, register_adapter
from security.classification import DataClassification


def _num(payload: Mapping[str, Any], key: str, default: Optional[float] = None) -> Optional[float]:
    value = payload.get(key, default)
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError(f"{key}: must be a number, got bool")
    try:
        return float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{key}: must be numeric, got {value!r}") from None


def _required_num(payload: Mapping[str, Any], key: str) -> float:
    if key not in payload:
        raise ValueError(f"missing required input '{key}'")
    return _num(payload, key)  # type: ignore[return-value]


def _rows(payload: Mapping[str, Any], key: str) -> List[Dict[str, Any]]:
    value = payload.get(key)
    if not isinstance(value, list) or not value:
        raise ValueError(f"missing or empty required input '{key}' (expected a non-empty list of rows)")
    for i, row in enumerate(value):
        if not isinstance(row, dict):
            raise ValueError(f"{key}[{i}]: must be an object")
    return value


# ═══════════════════════════════════════════════════════════════════════════
# WFM — Workforce Management / Erlang C
# ═══════════════════════════════════════════════════════════════════════════


class WFMAdapter(EngineAdapter):
    """Deterministic Erlang C staffing: maps target service level to agents."""

    engine_id = "wfm"
    display_name = "WFM Forecasting / Erlang C"
    capability_ids = ("wfm_forecast", "erlang_c", "staffing_optimization")
    owning_role_id = "ops_gm"
    data_classification = DataClassification.INTERNAL
    computation_method = "erlang_c"
    computation_formulas = (
        "offered_load_A = arrival_rate * aht",
        "erlang_c_probability_of_wait",
        "service_level = 1 - C * exp(-(N - A) * (target_time / aht))",
    )

    def validate(self, payload: Mapping[str, Any], sample_data_mode: bool) -> None:
        if "arrival_rate" not in payload and not (
            "contacts" in payload and "interval_minutes" in payload
        ):
            raise ValueError("missing required WFM inputs: arrival_rate (or contacts + interval_minutes)")
        if "average_handling_time" not in payload and "aht_seconds" not in payload:
            raise ValueError("missing required WFM input: average_handling_time (or aht_seconds)")
        if "service_level_target" not in payload:
            raise ValueError("missing required WFM input: service_level_target")

        arrival = self._arrival_rate(payload)
        aht = self._aht(payload)
        target = _required_num(payload, "service_level_target")
        if arrival <= 0:
            raise ValueError("arrival_rate must be > 0")
        if aht <= 0:
            raise ValueError("average_handling_time must be > 0")
        if not 0 < target < 1:
            raise ValueError("service_level_target must be in (0, 1)")

    def _arrival_rate(self, payload: Mapping[str, Any]) -> float:
        if "arrival_rate" in payload:
            return _required_num(payload, "arrival_rate")
        contacts = _required_num(payload, "contacts")
        interval = _required_num(payload, "interval_minutes")
        if interval <= 0:
            raise ValueError("interval_minutes must be > 0")
        return contacts / (interval / 60.0)

    def _aht(self, payload: Mapping[str, Any]) -> float:
        """AHT normalised to minutes, which is what the Erlang C engine expects."""
        if "average_handling_time" in payload:
            return _required_num(payload, "average_handling_time")
        seconds = _required_num(payload, "aht_seconds")
        if seconds <= 0:
            raise ValueError("aht_seconds must be > 0")
        return seconds / 60.0

    def compute(
        self, payload: Mapping[str, Any], sample_data_mode: bool
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        from engines.wfm.src.erlang_c import ErlangCEngine, ErlangCParameters

        arrival_rate = self._arrival_rate(payload)
        aht = self._aht(payload)
        target = _required_num(payload, "service_level_target")
        avg_calls = _num(payload, "average_calls_per_period", 17.0) or 17.0

        params = ErlangCParameters(
            arrival_rate=arrival_rate,
            average_handling_time=aht,
            service_level_target=target,
            average_calls_per_period=avg_calls,
        )
        engine = ErlangCEngine(params)
        raw = engine.optimize_agents()
        metrics = self._as_dict(raw)

        if "optimal_agents" not in metrics and "required_staffing" in metrics:
            metrics["optimal_agents"] = metrics["required_staffing"]

        offered_load = arrival_rate * aht
        metrics.setdefault("offered_load_erlangs", round(offered_load, 4))
        metrics.setdefault("service_level_target", target)

        return metrics, {
            "parameters": {
                "arrival_rate": arrival_rate,
                "average_handling_time_minutes": aht,
                "service_level_target": target,
                "average_calls_per_period": avg_calls,
            },
            "inputs_used": sorted(payload.keys()),
            "assumptions": (
                "Erlang C assumes Poisson arrivals and exponentially distributed handle times",
                "no shrinkage, breaks or absenteeism applied unless supplied in the payload",
            ),
        }

    @staticmethod
    def _as_dict(raw: Any) -> Dict[str, Any]:
        if isinstance(raw, dict):
            return dict(raw)
        if hasattr(raw, "__dict__"):
            return {k: v for k, v in vars(raw).items() if not k.startswith("_")}
        return {"result": str(raw)}

    def confidence(self, metrics: Mapping[str, Any]) -> Optional[float]:
        # Erlang C is closed-form; confidence reflects input completeness, not
        # model uncertainty. Missing shrinkage data caps it below 1.0.
        return 0.95 if metrics.get("optimal_agents") is not None else None

    def baseline_payload(self) -> Dict[str, Any]:
        return {
            "contacts": 340,
            "interval_minutes": 30,
            "aht_seconds": 330,
            "service_level_target": 0.8,
            "average_calls_per_period": 17,
            "data_mode": "sample",
        }


# ═══════════════════════════════════════════════════════════════════════════
# RTA — Real-Time Adherence
# ═══════════════════════════════════════════════════════════════════════════


class RTAAdapter(EngineAdapter):
    """Maps real-time agent state traces against the schedule baseline."""

    engine_id = "rta"
    display_name = "RTA Command Center — Adherence & Variance"
    capability_ids = ("rta_adherence", "schedule_tracking", "adherence_calculation")
    owning_role_id = "ops_gm"
    data_classification = DataClassification.INTERNAL
    computation_method = "rta_adherence_variance"
    computation_formulas = (
        "adherence_percentage = actual_hours / scheduled_hours * 100",
        "variance = actual_hours - scheduled_hours",
    )

    def validate(self, payload: Mapping[str, Any], sample_data_mode: bool) -> None:
        _rows(payload, "schedule")
        _rows(payload, "actual")

    def compute(
        self, payload: Mapping[str, Any], sample_data_mode: bool
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        import pandas as pd

        from engines.rta.src.calculations import create_rta_calculator

        schedule = pd.DataFrame(_rows(payload, "schedule"))
        actual = pd.DataFrame(_rows(payload, "actual"))

        threshold = _num(payload, "adherence_threshold", 0.85) or 0.85
        variance_threshold = _num(payload, "variance_threshold", 2.0) or 2.0
        calculator = create_rta_calculator(
            adherence_threshold=threshold, variance_threshold=variance_threshold
        )
        result = calculator.analyze(schedule, actual)

        metrics: Dict[str, Any] = {}
        for source in ("adherence_metrics", "schedule_metrics", "performance_metrics", "variance_analysis"):
            block = getattr(result, source, None)
            if isinstance(block, dict):
                for key, value in block.items():
                    metrics[f"{source[:-8] if source.endswith('_metrics') else source}.{key}"] = value
        metrics["confidence_score"] = getattr(result, "confidence_score", None)
        metrics["optimization_recommendations"] = list(
            getattr(result, "optimization_recommendations", []) or []
        )

        # Surface the headline number under a stable key for downstream gates.
        metrics["adherence_percentage"] = metrics.get(
            "adherence.average_adherence",
            metrics.get("adherence.adherence_percentage", metrics.get("adherence.overall_adherence")),
        )

        return metrics, {
            "parameters": {
                "adherence_threshold": threshold,
                "variance_threshold": variance_threshold,
                "schedule_rows": int(len(schedule)),
                "actual_rows": int(len(actual)),
            },
            "inputs_used": sorted(payload.keys()),
            "assumptions": (
                "schedule and actual rows are inner-joined on agent_id, date and hour",
                "rows without a matching counterpart are excluded from adherence",
            ),
        }

    def confidence(self, metrics: Mapping[str, Any]) -> Optional[float]:
        score = metrics.get("confidence_score")
        return float(score) if isinstance(score, (int, float)) else None

    def baseline_payload(self) -> Dict[str, Any]:
        schedule, actual = [], []
        for hour in range(9, 12):
            for agent in ("agent-1", "agent-2"):
                scheduled = 1.0
                schedule.append(
                    {"agent_id": agent, "date": "2026-09-07", "hour": hour, "scheduled_hours": scheduled}
                )
                actual.append(
                    {
                        "agent_id": agent,
                        "date": "2026-09-07",
                        "hour": hour,
                        "actual_hours": scheduled if agent == "agent-1" else scheduled * 0.82,
                    }
                )
        return {
            "schedule": schedule,
            "actual": actual,
            "adherence_threshold": 0.85,
            "variance_threshold": 2.0,
            "data_mode": "sample",
        }


# ═══════════════════════════════════════════════════════════════════════════
# CX — Churn Sentinel
# ═══════════════════════════════════════════════════════════════════════════


class CXAdapter(EngineAdapter):
    """Predictive churn-risk scoring from account telemetry."""

    engine_id = "cx"
    display_name = "CX Churn Sentinel — Risk Scoring"
    capability_ids = ("churn_risk_scoring", "risk_scoring", "cx_monitoring")
    owning_role_id = "ops_gm"
    data_classification = DataClassification.CLIENT_CONFIDENTIAL
    computation_method = "weighted_kpi_risk_scoring"
    computation_formulas = (
        "risk_score = sum(weight_k * normalised_kpi_k) / sum(weight_k)",
        "risk_level = bucket(risk_score)",
    )

    def validate(self, payload: Mapping[str, Any], sample_data_mode: bool) -> None:
        customers = payload.get("customers")
        if not isinstance(customers, list) or not customers:
            raise ValueError("missing or empty required input 'customers' (non-empty list of account records)")
        for i, customer in enumerate(customers):
            if not isinstance(customer, dict):
                raise ValueError(f"customers[{i}]: must be an object")
            if not customer.get("customer_id"):
                raise ValueError(f"customers[{i}]: missing customer_id")

    def compute(
        self, payload: Mapping[str, Any], sample_data_mode: bool
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        from engines.cx.src.risk_scorer import create_risk_scorer

        customers = [dict(c) for c in payload["customers"]]
        weights = payload.get("kpi_weights") or None

        scorer = create_risk_scorer(kpi_weights=weights)
        result = scorer.score_customers(customers)

        metrics: Dict[str, Any] = {}
        for attribute in (
            "total_customers",
            "average_risk_score",
            "high_risk_count",
            "medium_risk_count",
            "low_risk_count",
            "risk_distribution",
        ):
            if hasattr(result, attribute):
                metrics[attribute] = getattr(result, attribute)
        scored = getattr(result, "scored_customers", None)
        if scored is None:
            scored = getattr(result, "customer_scores", [])
        metrics["scored_customers"] = [
            c if isinstance(c, dict) else vars(c) for c in (scored or [])
        ]
        metrics["high_risk_ratio"] = (
            round(metrics["high_risk_count"] / metrics["total_customers"], 4)
            if metrics.get("total_customers")
            else 0.0
        )

        return metrics, {
            "parameters": {"kpi_weights": weights, "customer_count": len(customers)},
            "inputs_used": sorted(payload.keys()),
            "assumptions": (
                "risk is a weighted composite of supplied KPIs, not a causal model",
                "accounts with missing KPIs are scored on the KPIs present",
            ),
        }

    def confidence(self, metrics: Mapping[str, Any]) -> Optional[float]:
        total = metrics.get("total_customers") or 0
        if not total:
            return None
        # Confidence grows with sample size; below 10 accounts the score is
        # directional at best and downstream gates treat it as such.
        return round(min(0.5 + (total / 100.0), 0.95), 3)

    def baseline_payload(self) -> Dict[str, Any]:
        return {
            "customers": [
                {"customer_id": "CUST-001", "csat": 0.72, "sla": 0.86, "fcr": 0.81, "aht": 0.42},
                {"customer_id": "CUST-002", "csat": 0.51, "sla": 0.68, "fcr": 0.60, "aht": 0.63},
                {"customer_id": "CUST-003", "csat": 0.91, "sla": 0.95, "fcr": 0.90, "aht": 0.31},
                {"customer_id": "CUST-004", "csat": 0.64, "sla": 0.79, "fcr": 0.74, "aht": 0.55},
            ],
            "data_mode": "sample",
        }


# ═══════════════════════════════════════════════════════════════════════════
# CRM — Sales pipeline & customer support
# ═══════════════════════════════════════════════════════════════════════════


class CRMAdapter(EngineAdapter):
    """Pipeline analytics and lead qualification over the CRM engine."""

    engine_id = "crm"
    display_name = "CRM — Sales Pipeline & Customer Support"
    capability_ids = ("sales_pipeline", "customer_support", "crm_operations")
    owning_role_id = "sales_gm"
    data_classification = DataClassification.CLIENT_CONFIDENTIAL
    computation_method = "pipeline_analytics"
    computation_formulas = (
        "weighted_pipeline = sum(deal_value * stage_probability)",
        "win_rate = closed_won / (closed_won + closed_lost)",
    )

    def validate(self, payload: Mapping[str, Any], sample_data_mode: bool) -> None:
        if not payload.get("operation"):
            raise ValueError("missing required input 'operation' (analytics | score_lead | support_metrics)")
        operation = str(payload["operation"]).lower()
        if operation not in {"analytics", "score_lead", "support_metrics"}:
            raise ValueError(
                f"unsupported operation {operation!r} (expected analytics | score_lead | support_metrics)"
            )
        if operation == "score_lead":
            lead = payload.get("lead")
            if not isinstance(lead, dict) or not lead.get("lead_id"):
                raise ValueError("operation 'score_lead' requires a 'lead' object with lead_id")
        if operation == "support_metrics":
            _rows(payload, "tickets")

    def compute(
        self, payload: Mapping[str, Any], sample_data_mode: bool
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        operation = str(payload["operation"]).lower()

        if operation == "score_lead":
            return self._score_lead(payload)
        if operation == "support_metrics":
            return self._support_metrics(payload)
        return self._analytics(payload)

    # ── operations ──────────────────────────────────────────────────────────

    def _analytics(self, payload: Mapping[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        from engines.crm.src.sales_pipeline import Deal, Lead, SalesPipeline

        pipeline = SalesPipeline()
        for lead in payload.get("leads") or []:
            pipeline.add_lead(
                Lead(
                    lead_id=str(lead["lead_id"]),
                    name=str(lead.get("name", "")),
                    email=str(lead.get("email", "")),
                    company=str(lead.get("company", "")),
                    source=str(lead.get("source", "unknown")),
                    score=float(lead.get("score", 0.0)),
                    status=str(lead.get("status", "new")),
                )
            )
        for deal in payload.get("deals") or []:
            pipeline.create_deal(
                Deal(
                    lead_id=str(deal["lead_id"]),
                    deal_id=str(deal.get("deal_id", f"deal_{deal['lead_id']}")),
                    value=float(deal.get("value", 0.0)),
                    stage=str(deal.get("stage", "qualification")),
                    probability=float(deal.get("probability", 0.0)),
                    close_date=str(deal.get("close_date", "")),
                )
            )
        return pipeline.get_sales_analytics(), {
            "parameters": {"operation": "analytics"},
            "inputs_used": sorted(payload.keys()),
            "assumptions": ("stage probabilities supplied by the caller are authoritative",),
        }

    def _score_lead(self, payload: Mapping[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        from engines.crm.src.sales_pipeline import Lead, SalesPipeline

        raw = dict(payload["lead"])
        pipeline = SalesPipeline()
        lead = Lead(
            lead_id=str(raw["lead_id"]),
            name=str(raw.get("name", "")),
            email=str(raw.get("email", "")),
            company=str(raw.get("company", "")),
            source=str(raw.get("source", "unknown")),
            score=float(raw.get("score", 0.0)),
            status=str(raw.get("status", "new")),
        )
        pipeline.add_lead(lead)
        return pipeline.score_lead(lead.lead_id), {
            "parameters": {"operation": "score_lead", "lead_id": lead.lead_id},
            "inputs_used": sorted(payload.keys()),
            "assumptions": ("qualification score is a heuristic, not a propensity model",),
        }

    def _support_metrics(self, payload: Mapping[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        from engines.crm.src.customer_support import create_customer_support

        support = create_customer_support()
        tickets = _rows(payload, "tickets")
        created = 0
        for ticket in tickets:
            support.create_ticket(
                ticket_id=str(ticket.get("ticket_id", f"ticket_{created}")),
                customer_id=str(ticket.get("customer_id", "")),
                subject=str(ticket.get("subject", "")),
                description=str(ticket.get("description", "")),
                priority=str(ticket.get("priority", "medium")),
                category=str(ticket.get("category", "general")),
            )
            created += 1
        return support.get_support_metrics(), {
            "parameters": {"operation": "support_metrics", "ticket_count": created},
            "inputs_used": sorted(payload.keys()),
            "assumptions": ("metrics cover only the tickets supplied in this request",),
        }

    def confidence(self, metrics: Mapping[str, Any]) -> Optional[float]:
        return 0.8

    def baseline_payload(self) -> Dict[str, Any]:
        return {
            "operation": "analytics",
            "leads": [
                {"lead_id": "lead-1", "name": "Northwind", "source": "outbound", "score": 0.72, "status": "qualified"},
                {"lead_id": "lead-2", "name": "Contoso", "source": "inbound", "score": 0.55, "status": "new"},
            ],
            "deals": [
                {"lead_id": "lead-1", "deal_id": "deal-1", "value": 48000.0, "stage": "proposal", "probability": 0.6},
                {"lead_id": "lead-2", "deal_id": "deal-2", "value": 22000.0, "stage": "qualification", "probability": 0.25},
            ],
            "data_mode": "sample",
        }


# ═══════════════════════════════════════════════════════════════════════════
# Personnel — Talent acquisition & workforce planning
# ═══════════════════════════════════════════════════════════════════════════


class PersonnelAdapter(EngineAdapter):
    """Candidate assessment matrices, requisitions and workforce forecasting."""

    engine_id = "personnel"
    display_name = "Personnel — Talent Acquisition & Workforce Planning"
    capability_ids = ("talent_acquisition", "workforce_planning", "hiring_pipeline")
    owning_role_id = "hr_personnel_gm"
    data_classification = DataClassification.PERSONNEL_SENSITIVE
    computation_method = "workforce_planning"
    computation_formulas = (
        "skills_gap_score = 1 - (available_skill / required_skill)",
        "forecast_headcount = current_headcount * (1 + growth_rate)",
    )

    def validate(self, payload: Mapping[str, Any], sample_data_mode: bool) -> None:
        if not payload.get("operation"):
            raise ValueError("missing required input 'operation' (workforce_needs | sourcing_analytics)")
        operation = str(payload["operation"]).lower()
        if operation not in {"workforce_needs", "sourcing_analytics"}:
            raise ValueError(
                f"unsupported operation {operation!r} (expected workforce_needs | sourcing_analytics)"
            )
        if operation == "workforce_needs":
            if not payload.get("department"):
                raise ValueError("operation 'workforce_needs' requires 'department'")
            requirements = payload.get("requirements")
            if not isinstance(requirements, list) or not requirements:
                raise ValueError("operation 'workforce_needs' requires a non-empty 'requirements' list")

    def compute(
        self, payload: Mapping[str, Any], sample_data_mode: bool
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        operation = str(payload["operation"]).lower()

        if operation == "sourcing_analytics":
            from engines.personnel.src.talent_acquisition import create_talent_acquisition

            acquisition = create_talent_acquisition()
            return acquisition.get_sourcing_analytics(), {
                "parameters": {"operation": "sourcing_analytics"},
                "inputs_used": sorted(payload.keys()),
                "assumptions": ("analytics are scoped to candidates registered in this request",),
            }

        from engines.personnel.src.workforce_planning import StaffingRequirement, create_workforce_planning

        planning = create_workforce_planning()
        for index, req in enumerate(payload["requirements"]):
            salary = req.get("salary_range") or {}
            planning.add_staffing_requirement(
                StaffingRequirement(
                    requirement_id=str(req.get("requirement_id", f"req_{index}")),
                    position=str(req["position"]),
                    department=str(req.get("department", payload["department"])),
                    quantity=int(req.get("quantity", 1)),
                    skill_level=str(req.get("skill_level", "mid")),
                    salary_range={
                        "min": float(salary.get("min", 0.0)),
                        "max": float(salary.get("max", 0.0)),
                    },
                    timeline=str(req.get("timeline", "Q1")),
                    priority=str(req.get("priority", "medium")),
                )
            )
        period = int(_num(payload, "forecast_period", 4) or 4)
        metrics = planning.analyze_workforce_needs(str(payload["department"]), period)
        return metrics, {
            "parameters": {
                "operation": "workforce_needs",
                "department": payload["department"],
                "forecast_period": period,
            },
            "inputs_used": sorted(payload.keys()),
            "assumptions": ("forecast is linear in the supplied growth assumptions",),
        }

    def confidence(self, metrics: Mapping[str, Any]) -> Optional[float]:
        return 0.75

    def baseline_payload(self) -> Dict[str, Any]:
        return {
            "operation": "workforce_needs",
            "department": "customer_operations",
            "forecast_period": 4,
            "requirements": [
                {
                    "requirement_id": "req-1",
                    "position": "Customer Support Agent",
                    "department": "customer_operations",
                    "quantity": 6,
                    "skill_level": "mid",
                    "salary_range": {"min": 28000.0, "max": 36000.0},
                    "timeline": "Q4",
                    "priority": "high",
                }
            ],
            "data_mode": "sample",
        }


# ═══════════════════════════════════════════════════════════════════════════
# B2B — Client onboarding automation
# ═══════════════════════════════════════════════════════════════════════════


class B2BAdapter(EngineAdapter):
    """Client onboarding: SOP generation and staffing-plan construction."""

    engine_id = "b2b"
    display_name = "B2B Client Onboarding Automator"
    capability_ids = ("b2b_onboarding", "sop_generation", "b2b_handoff")
    owning_role_id = "sales_gm"
    data_classification = DataClassification.CLIENT_CONFIDENTIAL
    computation_method = "onboarding_automation"
    computation_formulas = (
        "role_count = f(client_size, complexity, requirements)",
        "total_cost = sum(role.rate * role.headcount * role.duration)",
    )

    def validate(self, payload: Mapping[str, Any], sample_data_mode: bool) -> None:
        if not payload.get("operation"):
            raise ValueError("missing required input 'operation' (sop | staffing_plan | client_summary)")
        operation = str(payload["operation"]).lower()
        if operation not in {"sop", "staffing_plan", "client_summary"}:
            raise ValueError(
                f"unsupported operation {operation!r} (expected sop | staffing_plan | client_summary)"
            )
        client = payload.get("client")
        if not isinstance(client, dict) or not client.get("client_id"):
            raise ValueError("missing required input 'client' (object with client_id)")

    def compute(
        self, payload: Mapping[str, Any], sample_data_mode: bool
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        from engines.b2b.src.automator import ClientProfile, create_automator

        raw = dict(payload["client"])
        automator = create_automator()
        automator.add_client(
            ClientProfile(
                client_id=str(raw["client_id"]),
                name=str(raw.get("name", raw["client_id"])),
                industry=str(raw.get("industry", "unspecified")),
                size=str(raw.get("size", "mid_market")),
                complexity=str(raw.get("complexity", "standard")),
                requirements=list(raw.get("requirements") or []),
            )
        )
        client_id = str(raw["client_id"])
        operation = str(payload["operation"]).lower()

        if operation == "sop":
            doc = automator.generate_sop(client_id)
            metrics = doc.to_dict() if hasattr(doc, "to_dict") else {"document": str(doc)}
        elif operation == "staffing_plan":
            workload = dict(payload.get("workload") or {})
            plan = automator.generate_staffing_plan(client_id, workload)
            metrics = plan.to_dict() if hasattr(plan, "to_dict") else {"plan": str(plan)}
        else:
            metrics = automator.get_client_summary(client_id)

        return metrics, {
            "parameters": {"operation": operation, "client_id": client_id},
            "inputs_used": sorted(payload.keys()),
            "assumptions": (
                "SOP and staffing plan are template-driven; a human approves before handoff",
            ),
        }

    def confidence(self, metrics: Mapping[str, Any]) -> Optional[float]:
        return 0.7

    def baseline_payload(self) -> Dict[str, Any]:
        return {
            "operation": "sop",
            "client": {
                "client_id": "client-sample",
                "name": "Sample Contact Centre",
                "industry": "telecommunications",
                "size": "mid_market",
                "complexity": "standard",
                "requirements": ["inbound_voice", "email_support"],
            },
            "data_mode": "sample",
        }


#: Registered adapter instances, in engine order.
WFM_ADAPTER = register_adapter(WFMAdapter())
RTA_ADAPTER = register_adapter(RTAAdapter())
CX_ADAPTER = register_adapter(CXAdapter())
CRM_ADAPTER = register_adapter(CRMAdapter())
PERSONNEL_ADAPTER = register_adapter(PersonnelAdapter())
B2B_ADAPTER = register_adapter(B2BAdapter())

ALL_ADAPTERS = (WFM_ADAPTER, RTA_ADAPTER, CX_ADAPTER, CRM_ADAPTER, PERSONNEL_ADAPTER, B2B_ADAPTER)


def install(engine: Any) -> None:
    """
    Wire every adapter into a C2 :class:`~control_plane.engine.Engine`.

    The control plane calls handlers with a ``Workflow``; adapters speak
    ``TaskRequest``. This bridge converts between the two, and converts an
    adapter refusal into a raised error so the engine's existing
    retry/dead-letter path handles it exactly as it would any other failure.
    """
    from contracts.task import CorrelationContext, TaskRequest

    for adapter in ALL_ADAPTERS:
        for capability in adapter.capability_ids:
            engine.register_handler(capability, _make_handler(adapter, capability, TaskRequest, CorrelationContext))


def _make_handler(adapter: EngineAdapter, capability: str, task_request_cls: Any, correlation_cls: Any):
    def handler(workflow: Any) -> Dict[str, Any]:
        request = task_request_cls(
            request_id=getattr(workflow, "workflow_id", "") or "",
            correlation=getattr(workflow, "correlation", None) or correlation_cls.new(),
            requesting_actor=getattr(workflow, "requesting_actor", "") or "",
            owning_role_id=getattr(workflow, "owning_role_id", "") or adapter.owning_role_id,
            capability=capability,
            input_payload=dict(getattr(workflow, "input_payload", {}) or {}),
            requires_approval=False,
            status="validated",
            created_at=getattr(workflow, "created_at", "") or "",
            tenant_id=getattr(workflow, "tenant_id", None),
            client_id=getattr(workflow, "client_id", None),
        )
        outcome = adapter.execute(request)
        if outcome.task_result.status != "succeeded":
            error = outcome.task_result.error
            raise RuntimeError(f"[{error.code}] {error.message}")
        return dict(outcome.engine_result.metrics)

    handler._adapter = adapter  # type: ignore[attr-defined]
    handler._capability = capability  # type: ignore[attr-defined]
    return handler


__all__ = [
    "ALL_ADAPTERS",
    "B2BAdapter",
    "B2B_ADAPTER",
    "CRMAdapter",
    "CRM_ADAPTER",
    "CXAdapter",
    "CX_ADAPTER",
    "PersonnelAdapter",
    "PERSONNEL_ADAPTER",
    "RTAAdapter",
    "RTA_ADAPTER",
    "WFMAdapter",
    "WFM_ADAPTER",
    "install",
]
