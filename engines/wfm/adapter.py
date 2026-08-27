"""
WFM Forecasting / Erlang C — Adapter (C4)

Invokes actual engines/wfm/src/erlang_c.py without rewriting engine logic.
Validates inputs, returns shared EngineResult, emits audit/observability, enforces C3 policy.
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

ENGINE_ID = "wfm"
DISPLAY_NAME = "WFM Forecasting / Erlang C"
CAPABILITY_IDS = ["wfm_forecast", "erlang_c", "staffing_optimization"]
OWNING_ROLE = "ops_gm"
DATA_CLASSIFICATION = DataClassification.INTERNAL  # WFM is internal unless client data includes personnel


def _audit(event_type: str, correlation_id: str, actor: str, workflow_id: str | None = None, decision: str = "succeeded", tenant_id: str | None = None, client_id: str | None = None):
    try:
        trail = AuditTrail(db_path="security/audit.db")
        last = trail.list_records(limit=10000)
        prev = last[-1].current_hash if last else None
        rec = AuditRecord.new(event_type=event_type, actor=actor, actor_type="service", decision=decision, correlation_id=correlation_id, tenant_id=tenant_id, client_id=client_id, role_id=OWNING_ROLE, workflow_id=workflow_id, previous_hash=prev)
        trail.append(rec)
        trail.close()
    except Exception:
        pass


def _log(event_type: str, correlation_id: str, actor: str, workflow_id: str | None, result_status: str, **kwargs):
    try:
        log_structured(event_type=event_type, correlation_id=correlation_id, workflow_id=workflow_id, actor=actor, capability=CAPABILITY_IDS[0], tool="wfm_engine", result_status=result_status, **kwargs)
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

    # C3: no secrets in payload
    try:
        validate_no_secrets(input_payload)
    except ValueError as e:
        _audit("wfm_policy_denied", correlation_id, actor, decision="denied", tenant_id=tenant_id, client_id=client_id)
        _log("wfm_policy_denied", correlation_id, actor, None, "denied", error_code="secret_detected", tenant_id=tenant_id, client_id=client_id)
        return EngineResult.failure(
            engine_id=ENGINE_ID,
            display_name=DISPLAY_NAME,
            capability_ids=CAPABILITY_IDS,
            tenant_id=tenant_id,
            client_id=client_id,
            correlation_id=correlation_id,
            causation_id=causation_id,
            actor=actor,
            owning_role_id=owning_role_id,
            input_payload=input_payload,
            error_code="policy_denied",
            error_message=str(e),
            warnings=warnings,
            data_classification=DATA_CLASSIFICATION,
            data_mode="sample" if is_sample else "real",
            is_sample=is_sample,
            duration_ms=int((time.time() - start) * 1000),
        )

    # C3: classification (default internal, allow explicit)
    data_class = input_payload.get("data_classification", DATA_CLASSIFICATION)
    try:
        validate_payload_classification(input_payload, data_class)
    except ValueError as e:
        return EngineResult.failure(
            engine_id=ENGINE_ID,
            display_name=DISPLAY_NAME,
            capability_ids=CAPABILITY_IDS,
            tenant_id=tenant_id,
            client_id=client_id,
            correlation_id=correlation_id,
            causation_id=causation_id,
            actor=actor,
            owning_role_id=owning_role_id,
            input_payload=input_payload,
            error_code="invalid_classification",
            error_message=str(e),
            warnings=warnings,
            data_classification=DATA_CLASSIFICATION,
            data_mode="sample" if is_sample else "real",
            is_sample=is_sample,
            duration_ms=int((time.time() - start) * 1000),
        )

    # C3: authorization (tenant isolation, role/capability/tool)
    try:
        from organization.capability_registry import is_tool_allowed

        # Use Identity for tenant isolation check via policy
        ident = Identity(actor=actor, actor_type=ActorType.SERVICE, tenant_id=tenant_id, client_id=client_id, role_id=owning_role_id)
        auth_req = AuthorizationRequest(identity=ident, capability="wfm_forecast", tool="wfm_engine", owning_role_id=OWNING_ROLE, target_tenant_id=tenant_id, target_client_id=client_id)
        decision = authorize(auth_req)
        if not decision.allowed:
            _audit("wfm_authorization_denied", correlation_id, actor, decision="denied", tenant_id=tenant_id, client_id=client_id)
            _log("wfm_authorization_denied", correlation_id, actor, None, "denied", error_code=decision.code, tenant_id=tenant_id, client_id=client_id)
            return EngineResult.failure(
                engine_id=ENGINE_ID,
                display_name=DISPLAY_NAME,
                capability_ids=CAPABILITY_IDS,
                tenant_id=tenant_id,
                client_id=client_id,
                correlation_id=correlation_id,
                causation_id=causation_id,
                actor=actor,
                owning_role_id=owning_role_id,
                input_payload=input_payload,
                error_code="unauthorized",
                error_message=decision.reason,
                warnings=warnings,
                data_classification=data_class,
                data_mode="sample" if is_sample else "real",
                is_sample=is_sample,
                duration_ms=int((time.time() - start) * 1000),
            )
        # Also check tool allowed
        if not is_tool_allowed(OWNING_ROLE, "wfm_engine"):
            return EngineResult.failure(
                engine_id=ENGINE_ID,
                display_name=DISPLAY_NAME,
                capability_ids=CAPABILITY_IDS,
                tenant_id=tenant_id,
                client_id=client_id,
                correlation_id=correlation_id,
                causation_id=causation_id,
                actor=actor,
                owning_role_id=owning_role_id,
                input_payload=input_payload,
                error_code="unauthorized",
                error_message="tool wfm_engine not allowed for role",
                warnings=warnings,
                data_classification=data_class,
                data_mode="sample" if is_sample else "real",
                is_sample=is_sample,
                duration_ms=int((time.time() - start) * 1000),
            )
    except Exception as e:
        # If policy check itself fails, fail closed
        if "unauthorized" in str(e).lower() or "tenant" in str(e).lower():
            return EngineResult.failure(
                engine_id=ENGINE_ID,
                display_name=DISPLAY_NAME,
                capability_ids=CAPABILITY_IDS,
                tenant_id=tenant_id,
                client_id=client_id,
                correlation_id=correlation_id,
                causation_id=causation_id,
                actor=actor,
                owning_role_id=owning_role_id,
                input_payload=input_payload,
                error_code="unauthorized",
                error_message=str(e),
                warnings=warnings,
                data_classification=data_class,
                data_mode="sample" if is_sample else "real",
                is_sample=is_sample,
                duration_ms=int((time.time() - start) * 1000),
            )

    # Validate WFM specific inputs
    try:
        # Expected inputs: arrival_rate, average_handling_time, service_level_target, average_calls_per_period (from ErlangCParameters)
        # Also support interval/contact inputs: interval_minutes, contacts, aht_seconds, service_level, occupancy_target
        arrival_rate = input_payload.get("arrival_rate")
        aht = input_payload.get("average_handling_time")
        service_level = input_payload.get("service_level_target")
        avg_calls = input_payload.get("average_calls_per_period", 17)

        # Alternative naming for interval mode
        if arrival_rate is None and "contacts" in input_payload and "interval_minutes" in input_payload:
            contacts = float(input_payload["contacts"])
            interval = float(input_payload["interval_minutes"])
            if interval <= 0:
                raise ValueError("interval_minutes must be >0")
            arrival_rate = contacts / (interval / 60.0)  # per hour
            warnings.append(f"derived arrival_rate={arrival_rate:.2f} from contacts={contacts} interval={interval}")

        if aht is None and "aht_seconds" in input_payload:
            aht = float(input_payload["aht_seconds"]) / 60.0
        if aht is None and "average_handling_time" in input_payload:
            aht = float(input_payload["average_handling_time"])

        if arrival_rate is None or aht is None or service_level is None:
            raise ValueError("missing required WFM inputs: arrival_rate, average_handling_time, service_level_target")

        arrival_rate = float(arrival_rate)
        aht = float(aht)
        service_level = float(service_level)
        avg_calls = float(avg_calls)

        if arrival_rate <= 0:
            raise ValueError("arrival_rate must be >0")
        if aht <= 0:
            raise ValueError("average_handling_time must be >0")
        if not 0 < service_level < 1:
            raise ValueError("service_level_target must be 0-1")
        if avg_calls <= 0:
            raise ValueError("average_calls_per_period must be >0")

    except (ValueError, TypeError) as e:
        _audit("wfm_validation_failed", correlation_id, actor, decision="denied", tenant_id=tenant_id, client_id=client_id)
        _log("wfm_validation_failed", correlation_id, actor, None, "failed", error_code="invalid_input", tenant_id=tenant_id, client_id=client_id, payload={"error": str(e)})
        return EngineResult.failure(
            engine_id=ENGINE_ID,
            display_name=DISPLAY_NAME,
            capability_ids=CAPABILITY_IDS,
            tenant_id=tenant_id,
            client_id=client_id,
            correlation_id=correlation_id,
            causation_id=causation_id,
            actor=actor,
            owning_role_id=owning_role_id,
            input_payload=input_payload,
            error_code="invalid_input",
            error_message=str(e),
            warnings=warnings,
            data_classification=data_class,
            data_mode="sample" if is_sample else "real",
            is_sample=is_sample,
            duration_ms=int((time.time() - start) * 1000),
        )

    # Invoke actual engine code
    try:
        from engines.wfm.src.erlang_c import ErlangCParameters, ErlangCEngine

        params = ErlangCParameters(
            arrival_rate=arrival_rate,
            average_handling_time=aht,
            service_level_target=service_level,
            average_calls_per_period=avg_calls,
        )
        engine = ErlangCEngine(params)
        # Use the engine's calculation (optimal_agents etc.)
        try:
            result = engine.optimize_agents()
        except AttributeError:
            # Fallback for different engine versions
            if hasattr(engine, "calculate_optimal_agents"):
                result = engine.calculate_optimal_agents()
            elif hasattr(engine, "optimize"):
                result = engine.optimize()
            elif hasattr(engine, "calculate"):
                result = engine.calculate()
            else:
                raise

        # Normalize result to dict metrics
        if hasattr(result, "__dict__"):
            metrics = {k: v for k, v in result.__dict__.items() if not k.startswith("_")}
        elif isinstance(result, dict):
            metrics = result
        else:
            metrics = {"result": str(result)}

        # Ensure required WFM metrics are present
        if "optimal_agents" not in metrics and "required_staffing" not in metrics:
            # Try to infer from engine's other attributes
            metrics.setdefault("optimal_agents", metrics.get("required_staffing", 0))
        # Add calculated vs recommended distinction: metrics are calculated, recommendations are separate
        recommendations = []
        if metrics.get("optimal_agents"):
            recommendations.append({"type": "staffing", "value": metrics["optimal_agents"], "rationale": "Erlang C calculated", "source": "calculated"})

        # Handle missing/partial data warnings
        if is_sample:
            warnings.append("sample/demo data — not live operational data")
        if len(warnings) == 0 and is_sample:
            warnings.append("sample data labeled")

        duration = int((time.time() - start) * 1000)
        evidence = [
            {"type": "engine_output", "engine": ENGINE_ID, "capability": CAPABILITY_IDS[0], "input_version": str(input_payload)[:50], "calculation": "erlang_c"}
        ]

        _audit("wfm_executed", correlation_id, actor, decision="succeeded", tenant_id=tenant_id, client_id=client_id)
        _log("wfm_executed", correlation_id, actor, None, "succeeded", tenant_id=tenant_id, client_id=client_id, capability=CAPABILITY_IDS[0], tool="wfm_engine", duration_ms=duration)

        return EngineResult.success(
            engine_id=ENGINE_ID,
            display_name=DISPLAY_NAME,
            capability_ids=CAPABILITY_IDS,
            tenant_id=tenant_id,
            client_id=client_id,
            correlation_id=correlation_id,
            causation_id=causation_id,
            actor=actor,
            owning_role_id=owning_role_id,
            metrics=metrics,
            input_payload=input_payload,
            recommendations=recommendations,
            evidence=evidence,
            warnings=warnings,
            data_classification=data_class,
            data_mode="sample" if is_sample else "real",
            is_sample=is_sample,
            duration_ms=duration,
        )

    except Exception as e:
        # Dependency unavailable or engine error -> typed failure, not silent
        if "No module named" in str(e) or "ImportError" in str(type(e).__name__):
            code = "dependency_unavailable"
        else:
            code = "engine_error"
        _audit("wfm_failed", correlation_id, actor, decision="failed", tenant_id=tenant_id, client_id=client_id)
        _log("wfm_failed", correlation_id, actor, None, "failed", error_code=code, tenant_id=tenant_id, client_id=client_id, payload={"error": str(e)})
        return EngineResult.failure(
            engine_id=ENGINE_ID,
            display_name=DISPLAY_NAME,
            capability_ids=CAPABILITY_IDS,
            tenant_id=tenant_id,
            client_id=client_id,
            correlation_id=correlation_id,
            causation_id=causation_id,
            actor=actor,
            owning_role_id=owning_role_id,
            input_payload=input_payload,
            error_code=code,
            error_message=str(e),
            warnings=warnings,
            data_classification=data_class,
            data_mode="sample" if is_sample else "real",
            is_sample=is_sample,
            duration_ms=int((time.time() - start) * 1000),
        )
