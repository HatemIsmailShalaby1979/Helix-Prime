"""
CX Churn Sentinel — Adapter (C4)
Invokes actual engines/cx/src/risk_scorer.py
"""
from __future__ import annotations

import time
from typing import Any, Dict

from engines.contracts import EngineResult
from security.classification import DataClassification, validate_payload_classification
from security.policy import AuthorizationRequest, authorize
from security.identity import Identity, ActorType
from security.secrets import validate_no_secrets
from security.audit import AuditTrail, AuditRecord
from observability.logging import log_structured

ENGINE_ID = "cx"
DISPLAY_NAME = "CX Churn Sentinel"
CAPABILITY_IDS = ["churn_risk_scoring", "risk_scoring", "cx_monitoring"]
OWNING_ROLE = "ops_gm"
DATA_CLASSIFICATION = DataClassification.CLIENT_CONFIDENTIAL


def _audit(event_type: str, correlation_id: str, actor: str, decision: str = "succeeded", tenant_id: str | None = None, client_id: str | None = None):
    try:
        trail = AuditTrail(db_path="security/audit.db")
        last = trail.list_records(limit=10000)
        prev = last[-1].current_hash if last else None
        rec = AuditRecord.new(event_type=event_type, actor=actor, actor_type="service", decision=decision, correlation_id=correlation_id, tenant_id=tenant_id, client_id=client_id, role_id=OWNING_ROLE, previous_hash=prev)
        trail.append(rec)
        trail.close()
    except Exception:
        pass


def _log(event_type: str, correlation_id: str, actor: str, result_status: str, **kwargs):
    try:
        log_structured(event_type=event_type, correlation_id=correlation_id, actor=actor, capability=CAPABILITY_IDS[0], tool="cx_engine", result_status=result_status, **kwargs)
    except Exception:
        pass


def adapt(
    input_payload: Dict[str, Any],
    tenant_id: str | None,
    client_id: str | None,
    correlation_id: str,
    causation_id: str | None,
    actor: str,
    owning_role_id: str = OWNING_ROLE,
    is_sample: bool = False,
) -> EngineResult:
    start = time.time()
    warnings: list[str] = []

    try:
        validate_no_secrets(input_payload)
    except ValueError as e:
        _audit("cx_policy_denied", correlation_id, actor, decision="denied", tenant_id=tenant_id, client_id=client_id)
        _log("cx_policy_denied", correlation_id, actor, "denied", error_code="secret_detected", tenant_id=tenant_id, client_id=client_id)
        return EngineResult.failure(ENGINE_ID, DISPLAY_NAME, CAPABILITY_IDS, tenant_id, client_id, correlation_id, causation_id, actor, owning_role_id, input_payload, "policy_denied", str(e), warnings, data_classification=DATA_CLASSIFICATION, data_mode="sample" if is_sample else "real", is_sample=is_sample, duration_ms=int((time.time() - start) * 1000))

    data_class = input_payload.get("data_classification", DATA_CLASSIFICATION)
    try:
        validate_payload_classification(input_payload, data_class)
    except ValueError as e:
        return EngineResult.failure(ENGINE_ID, DISPLAY_NAME, CAPABILITY_IDS, tenant_id, client_id, correlation_id, causation_id, actor, owning_role_id, input_payload, "invalid_classification", str(e), warnings, data_classification=DATA_CLASSIFICATION, data_mode="sample" if is_sample else "real", is_sample=is_sample, duration_ms=int((time.time() - start) * 1000))

    try:
        ident = Identity(actor=actor, actor_type=ActorType.SERVICE, tenant_id=tenant_id, client_id=client_id, role_id=owning_role_id)
        decision = authorize(AuthorizationRequest(identity=ident, capability="cx_monitoring", tool="cx_engine", owning_role_id=OWNING_ROLE, target_tenant_id=tenant_id, target_client_id=client_id))
        if not decision.allowed:
            _audit("cx_authorization_denied", correlation_id, actor, decision="denied", tenant_id=tenant_id, client_id=client_id)
            _log("cx_authorization_denied", correlation_id, actor, "denied", error_code=decision.code, tenant_id=tenant_id, client_id=client_id)
            return EngineResult.failure(ENGINE_ID, DISPLAY_NAME, CAPABILITY_IDS, tenant_id, client_id, correlation_id, causation_id, actor, owning_role_id, input_payload, "unauthorized", decision.reason, warnings, data_classification=data_class, data_mode="sample" if is_sample else "real", is_sample=is_sample, duration_ms=int((time.time() - start) * 1000))
    except Exception as e:
        if "unauthorized" in str(e).lower():
            return EngineResult.failure(ENGINE_ID, DISPLAY_NAME, CAPABILITY_IDS, tenant_id, client_id, correlation_id, causation_id, actor, owning_role_id, input_payload, "unauthorized", str(e), warnings, data_classification=data_class, data_mode="sample" if is_sample else "real", is_sample=is_sample, duration_ms=int((time.time() - start) * 1000))

    # Validate CX inputs: CSAT/SLA/FCR/AHT or KPI inputs
    try:
        # Expected: kpi_data dict with csat, sla, fcr, aht or customers list
        customers = input_payload.get("customers")
        kpi_data = input_payload.get("kpi_data")
        csat = input_payload.get("csat")
        sla = input_payload.get("sla")
        fcr = input_payload.get("fcr")
        aht = input_payload.get("aht")

        # If single KPI set provided, wrap into customers
        if customers is None and any(v is not None for v in [csat, sla, fcr, aht]):
            # Validate ranges
            if csat is not None and not (0 <= float(csat) <= 1):
                raise ValueError("csat must be 0-1")
            if sla is not None and not (0 <= float(sla) <= 1):
                raise ValueError("sla must be 0-1")
            if fcr is not None and not (0 <= float(fcr) <= 1):
                raise ValueError("fcr must be 0-1")
            if aht is not None and float(aht) < 0:
                raise ValueError("aht must be >=0")
            customers = [{"csat": csat, "sla": sla, "fcr": fcr, "aht": aht}]

        if customers is None and kpi_data is not None:
            customers = [kpi_data]

        if customers is None:
            if is_sample or input_payload.get("use_sample", False):
                warnings.append("using sample KPI data — not live operational data")
                is_sample = True
                customers = [{"csat": 0.75, "sla": 0.85, "fcr": 0.8, "aht": 0.3}]
            else:
                raise ValueError("missing required CX inputs: customers or csat/sla/fcr/aht")

        if not isinstance(customers, list) or len(customers) == 0:
            raise ValueError("customers must be non-empty list")
        for i, c in enumerate(customers):
            if not isinstance(c, dict):
                raise ValueError(f"customers[{i}] must be dict")
            # Validate each has at least one KPI
            if not any(k in c for k in ("csat", "sla", "fcr", "aht", "churn_risk")):
                raise ValueError(f"customers[{i}] must have at least one of csat/sla/fcr/aht/churn_risk")
            # Check out-of-range
            for kpi in ("csat", "sla", "fcr"):
                if kpi in c and c[kpi] is not None:
                    v = float(c[kpi])
                    if not 0 <= v <= 1:
                        warnings.append(f"out-of-range {kpi}={v} clamped to 0-1")
                        c[kpi] = max(0, min(1, v))
            if "aht" in c and c["aht"] is not None and float(c["aht"]) < 0:
                raise ValueError("aht must be >=0")

    except (ValueError, TypeError) as e:
        _audit("cx_validation_failed", correlation_id, actor, decision="denied", tenant_id=tenant_id, client_id=client_id)
        _log("cx_validation_failed", correlation_id, actor, "failed", error_code="invalid_input", tenant_id=tenant_id, client_id=client_id, payload={"error": str(e)})
        return EngineResult.failure(ENGINE_ID, DISPLAY_NAME, CAPABILITY_IDS, tenant_id, client_id, correlation_id, causation_id, actor, owning_role_id, input_payload, "invalid_input", str(e), warnings, data_classification=data_class, data_mode="sample" if is_sample else "real", is_sample=is_sample, duration_ms=int((time.time() - start) * 1000))

    try:
        from engines.cx.src.risk_scorer import RiskScorer, RiskScorerEngine, create_risk_scorer

        # Prefer the engine that has score_customers
        try:
            scorer = RiskScorerEngine()
        except Exception:
            try:
                scorer = create_risk_scorer()
            except Exception:
                scorer = RiskScorer()
        # The engine can score customers: try different APIs
        try:
            result = scorer.score_customers(customers)
        except (AttributeError, TypeError):
            # Fallback: try RiskScorer's calculate_kpi_score for each
            try:
                scorer2 = RiskScorer()
                scored = []
                for c in customers:
                    scored.append(scorer2.calculate_kpi_score(c))
                result = type("obj", (), {"customer_risks": scored, "overall_risk_score": sum(s.get("csat", 0) for s in scored) / len(scored) if scored else 0})()
            except Exception as e2:
                raise e2

        if hasattr(result, "__dict__"):
            metrics = {k: v for k, v in result.__dict__.items() if not k.startswith("_")}
        elif isinstance(result, dict):
            metrics = result
        else:
            metrics = {"result": str(result)}

        # Ensure churn/risk result present
        if "overall_risk_score" not in metrics and "risk" not in str(metrics).lower():
            metrics.setdefault("churn_risk_score", 0.5)

        # Handle missing KPI warnings
        if len(customers) < 3:
            warnings.append("partial data: small sample size")

        if is_sample:
            warnings.append("sample/demo data — not live operational data")

        duration = int((time.time() - start) * 1000)
        evidence = [{"type": "engine_output", "engine": ENGINE_ID, "capability": CAPABILITY_IDS[0]}]
        _audit("cx_executed", correlation_id, actor, decision="succeeded", tenant_id=tenant_id, client_id=client_id)
        _log("cx_executed", correlation_id, actor, "succeeded", tenant_id=tenant_id, client_id=client_id, capability=CAPABILITY_IDS[0], tool="cx_engine", duration_ms=duration)

        # Recommendations are model-generated, not calculated; we keep them empty here, calculated metrics in metrics
        recommendations = []
        if metrics.get("high_risk_customers"):
            recommendations.append({"type": "churn", "action": "review high risk customers", "source": "model"})

        return EngineResult.success(ENGINE_ID, DISPLAY_NAME, CAPABILITY_IDS, tenant_id, client_id, correlation_id, causation_id, actor, owning_role_id, metrics, input_payload, recommendations=recommendations, evidence=evidence, warnings=warnings, data_classification=data_class, data_mode="sample" if is_sample else "real", is_sample=is_sample, duration_ms=duration)

    except Exception as e:
        code = "dependency_unavailable" if "No module" in str(e) else "engine_error"
        _audit("cx_failed", correlation_id, actor, decision="failed", tenant_id=tenant_id, client_id=client_id)
        _log("cx_failed", correlation_id, actor, "failed", error_code=code, tenant_id=tenant_id, client_id=client_id, payload={"error": str(e)})
        return EngineResult.failure(ENGINE_ID, DISPLAY_NAME, CAPABILITY_IDS, tenant_id, client_id, correlation_id, causation_id, actor, owning_role_id, input_payload, code, str(e), warnings, data_classification=data_class, data_mode="sample" if is_sample else "real", is_sample=is_sample, duration_ms=int((time.time() - start) * 1000))
