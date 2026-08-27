"""
RTA Command Center — Adapter (C4)
Invokes actual engines/rta/src/calculations.py
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

ENGINE_ID = "rta"
DISPLAY_NAME = "RTA Command Center"
CAPABILITY_IDS = ["rta_adherence", "schedule_tracking", "adherence_calculation"]
OWNING_ROLE = "ops_gm"
DATA_CLASSIFICATION = DataClassification.INTERNAL


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
        log_structured(event_type=event_type, correlation_id=correlation_id, workflow_id=workflow_id, actor=actor, capability=CAPABILITY_IDS[0], tool="rta_engine", result_status=result_status, **kwargs)
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
        _audit("rta_policy_denied", correlation_id, actor, decision="denied", tenant_id=tenant_id, client_id=client_id)
        _log("rta_policy_denied", correlation_id, actor, None, "denied", error_code="secret_detected", tenant_id=tenant_id, client_id=client_id)
        return EngineResult.failure(ENGINE_ID, DISPLAY_NAME, CAPABILITY_IDS, tenant_id, client_id, correlation_id, causation_id, actor, owning_role_id, input_payload, "policy_denied", str(e), warnings, data_classification=DATA_CLASSIFICATION, data_mode="sample" if is_sample else "real", is_sample=is_sample, duration_ms=int((time.time() - start) * 1000))

    data_class = input_payload.get("data_classification", DATA_CLASSIFICATION)
    try:
        validate_payload_classification(input_payload, data_class)
    except ValueError as e:
        return EngineResult.failure(ENGINE_ID, DISPLAY_NAME, CAPABILITY_IDS, tenant_id, client_id, correlation_id, causation_id, actor, owning_role_id, input_payload, "invalid_classification", str(e), warnings, data_classification=DATA_CLASSIFICATION, data_mode="sample" if is_sample else "real", is_sample=is_sample, duration_ms=int((time.time() - start) * 1000))

    try:
        ident = Identity(actor=actor, actor_type=ActorType.SERVICE, tenant_id=tenant_id, client_id=client_id, role_id=owning_role_id)
        decision = authorize(AuthorizationRequest(identity=ident, capability="rta_adherence", tool="rta_engine", owning_role_id=OWNING_ROLE, target_tenant_id=tenant_id, target_client_id=client_id))
        if not decision.allowed:
            _audit("rta_authorization_denied", correlation_id, actor, decision="denied", tenant_id=tenant_id, client_id=client_id)
            _log("rta_authorization_denied", correlation_id, actor, None, "denied", error_code=decision.code, tenant_id=tenant_id, client_id=client_id)
            return EngineResult.failure(ENGINE_ID, DISPLAY_NAME, CAPABILITY_IDS, tenant_id, client_id, correlation_id, causation_id, actor, owning_role_id, input_payload, "unauthorized", decision.reason, warnings, data_classification=data_class, data_mode="sample" if is_sample else "real", is_sample=is_sample, duration_ms=int((time.time() - start) * 1000))
    except Exception as e:
        if "unauthorized" in str(e).lower():
            return EngineResult.failure(ENGINE_ID, DISPLAY_NAME, CAPABILITY_IDS, tenant_id, client_id, correlation_id, causation_id, actor, owning_role_id, input_payload, "unauthorized", str(e), warnings, data_classification=data_class, data_mode="sample" if is_sample else "real", is_sample=is_sample, duration_ms=int((time.time() - start) * 1000))

    # Validate RTA specific inputs: schedule and actual adherence inputs
    try:
        schedule = input_payload.get("schedule")
        actual = input_payload.get("actual")
        # Alternative: schedule_data / actual_data as DataFrame-like dicts
        if schedule is None and "schedule_data" in input_payload:
            schedule = input_payload["schedule_data"]
        if actual is None and "actual_data" in input_payload:
            actual = input_payload["actual_data"]

        if schedule is None or actual is None:
            # For C4, allow sample data if not provided, but warn and label as sample
            if is_sample or input_payload.get("use_sample", False):
                warnings.append("using sample schedule/actual data — not live operational data")
                is_sample = True
                # Create minimal sample DataFrames
                import pandas as pd
                import numpy as np

                np.random.seed(42)
                n = 5
                schedule = pd.DataFrame({"agent_id": [f"A{i}" for i in range(n)], "scheduled_min": [480] * n, "date": ["2026-08-27"] * n, "hour": [9] * n, "scheduled_hours": [8] * n})
                actual = pd.DataFrame({"agent_id": [f"A{i}" for i in range(n)], "logged_min": [460] * n, "productive_min": [450] * n, "date": ["2026-08-27"] * n, "hour": [9] * n, "actual_hours": [7.5] * n})
            else:
                raise ValueError("missing required RTA inputs: schedule and actual (or schedule_data/actual_data)")

        # Validate they are not empty
        if hasattr(schedule, "__len__") and len(schedule) == 0:
            raise ValueError("schedule data is empty")
        if hasattr(actual, "__len__") and len(actual) == 0:
            raise ValueError("actual data is empty")

    except (ValueError, TypeError) as e:
        _audit("rta_validation_failed", correlation_id, actor, decision="denied", tenant_id=tenant_id, client_id=client_id)
        _log("rta_validation_failed", correlation_id, actor, None, "failed", error_code="invalid_input", tenant_id=tenant_id, client_id=client_id, payload={"error": str(e)})
        return EngineResult.failure(ENGINE_ID, DISPLAY_NAME, CAPABILITY_IDS, tenant_id, client_id, correlation_id, causation_id, actor, owning_role_id, input_payload, "invalid_input", str(e), warnings, data_classification=data_class, data_mode="sample" if is_sample else "real", is_sample=is_sample, duration_ms=int((time.time() - start) * 1000))

    # Invoke actual engine code
    try:
        from engines.rta.src.calculations import RTACalculator
        import pandas as pd

        calc = RTACalculator(adherence_threshold=0.85, variance_threshold=2.0)
        # The engine expects DataFrames with specific columns
        # If schedule/actual are dicts, convert
        if isinstance(schedule, dict):
            schedule = pd.DataFrame(schedule)
        if isinstance(actual, dict):
            actual = pd.DataFrame(actual)

        # Try to call the engine's method
        try:
            result = calc.calculate_adherence(schedule, actual)
        except TypeError:
            # Alternative API
            result = calc.analyze(schedule, actual) if hasattr(calc, "analyze") else calc.calculate(schedule, actual)

        # Normalize result to metrics
        if isinstance(result, dict):
            metrics = result
        elif hasattr(result, "__dict__"):
            metrics = {k: v for k, v in result.__dict__.items() if not k.startswith("_")}
            # Flatten adherence_metrics if present
            if "adherence_metrics" in metrics and isinstance(metrics["adherence_metrics"], dict):
                metrics.update(metrics["adherence_metrics"])
        else:
            metrics = {"result": str(result)}

        # Ensure adherence/variance result present
        if "adherence" not in str(metrics).lower() and "overall" not in str(metrics).lower():
            metrics.setdefault("adherence_result", str(metrics)[:200])

        if is_sample:
            warnings.append("sample/demo data — not live operational data")

        duration = int((time.time() - start) * 1000)
        evidence = [{"type": "engine_output", "engine": ENGINE_ID, "capability": CAPABILITY_IDS[0]}]

        _audit("rta_executed", correlation_id, actor, decision="succeeded", tenant_id=tenant_id, client_id=client_id)
        _log("rta_executed", correlation_id, actor, None, "succeeded", tenant_id=tenant_id, client_id=client_id, capability=CAPABILITY_IDS[0], tool="rta_engine", duration_ms=duration)

        return EngineResult.success(ENGINE_ID, DISPLAY_NAME, CAPABILITY_IDS, tenant_id, client_id, correlation_id, causation_id, actor, owning_role_id, metrics, input_payload, warnings=warnings, evidence=evidence, data_classification=data_class, data_mode="sample" if is_sample else "real", is_sample=is_sample, duration_ms=duration)

    except Exception as e:
        code = "dependency_unavailable" if "No module" in str(e) else "engine_error"
        _audit("rta_failed", correlation_id, actor, decision="failed", tenant_id=tenant_id, client_id=client_id)
        _log("rta_failed", correlation_id, actor, None, "failed", error_code=code, tenant_id=tenant_id, client_id=client_id, payload={"error": str(e)})
        return EngineResult.failure(ENGINE_ID, DISPLAY_NAME, CAPABILITY_IDS, tenant_id, client_id, correlation_id, causation_id, actor, owning_role_id, input_payload, code, str(e), warnings, data_classification=data_class, data_mode="sample" if is_sample else "real", is_sample=is_sample, duration_ms=int((time.time() - start) * 1000))
