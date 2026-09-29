"""
CRM Engine — Adapter (C4)
Invokes actual engines/crm/src/sales_pipeline.py and customer_support.py
Client-confidential and financial classification handling.
"""
from __future__ import annotations

import time
from typing import Any, Dict

from engines.contracts import EngineResult
from observability.logging import log_structured
from security.audit import AuditRecord, AuditTrail
from security.classification import DataClassification, validate_payload_classification
from security.identity import ActorType, Identity
from security.policy import AuthorizationRequest, authorize
from security.secrets import validate_no_secrets

ENGINE_ID = "crm"
DISPLAY_NAME = "CRM Engine"
CAPABILITY_IDS = ["sales_pipeline", "customer_support", "crm_operations"]
OWNING_ROLE = "sales_gm"
DATA_CLASSIFICATION = DataClassification.CLIENT_CONFIDENTIAL


def _audit(
    event_type: str,
    correlation_id: str,
    actor: str,
    decision: str = "succeeded",
    tenant_id: str | None = None,
    client_id: str | None = None,
):
    try:
        trail = AuditTrail(db_path="security/audit.db")
        last = trail.list_records(limit=10000)
        prev = last[-1].current_hash if last else None
        rec = AuditRecord.new(
            event_type=event_type,
            actor=actor,
            actor_type="service",
            decision=decision,
            correlation_id=correlation_id,
            tenant_id=tenant_id,
            client_id=client_id,
            role_id=OWNING_ROLE,
            previous_hash=prev,
        )
        trail.append(rec)
        trail.close()
    except Exception:
        pass


def _log(event_type: str, correlation_id: str, actor: str, result_status: str, **kwargs):
    try:
        log_structured(
            event_type=event_type,
            correlation_id=correlation_id,
            actor=actor,
            capability=CAPABILITY_IDS[0],
            tool="crm_engine",
            result_status=result_status,
            **kwargs,
        )
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
        _audit(
            "crm_policy_denied",
            correlation_id,
            actor,
            decision="denied",
            tenant_id=tenant_id,
            client_id=client_id,
        )
        _log(
            "crm_policy_denied",
            correlation_id,
            actor,
            "denied",
            error_code="secret_detected",
            tenant_id=tenant_id,
            client_id=client_id,
        )
        return EngineResult.failure(
            ENGINE_ID,
            DISPLAY_NAME,
            CAPABILITY_IDS,
            tenant_id,
            client_id,
            correlation_id,
            causation_id,
            actor,
            owning_role_id,
            input_payload,
            "policy_denied",
            str(e),
            warnings,
            data_classification=DATA_CLASSIFICATION,
            data_mode="sample" if is_sample else "real",
            is_sample=is_sample,
            duration_ms=int((time.time() - start) * 1000),
        )

    data_class = input_payload.get("data_classification", DATA_CLASSIFICATION)
    # CRM can be client_confidential or financial; validate if provided is one of those or related
    try:
        validate_payload_classification(input_payload, data_class)
        # Additional check: financial data must be classified as financial or client_confidential
        if "deal_value" in str(input_payload).lower() and data_class not in (
            DataClassification.FINANCIAL,
            DataClassification.CLIENT_CONFIDENTIAL,
        ):
            warnings.append(
                f"financial data should be {DataClassification.FINANCIAL}, got {data_class}"
            )
    except ValueError as e:
        return EngineResult.failure(
            ENGINE_ID,
            DISPLAY_NAME,
            CAPABILITY_IDS,
            tenant_id,
            client_id,
            correlation_id,
            causation_id,
            actor,
            owning_role_id,
            input_payload,
            "invalid_classification",
            str(e),
            warnings,
            data_classification=DATA_CLASSIFICATION,
            data_mode="sample" if is_sample else "real",
            is_sample=is_sample,
            duration_ms=int((time.time() - start) * 1000),
        )

    try:
        ident = Identity(
            actor=actor,
            actor_type=ActorType.SERVICE,
            tenant_id=tenant_id,
            client_id=client_id,
            role_id=owning_role_id,
        )
        decision = authorize(
            AuthorizationRequest(
                identity=ident,
                capability="sales_pipeline",
                tool="crm_engine",
                owning_role_id=OWNING_ROLE,
                target_tenant_id=tenant_id,
                target_client_id=client_id,
            )
        )
        if not decision.allowed:
            _audit(
                "crm_authorization_denied",
                correlation_id,
                actor,
                decision="denied",
                tenant_id=tenant_id,
                client_id=client_id,
            )
            _log(
                "crm_authorization_denied",
                correlation_id,
                actor,
                "denied",
                error_code=decision.code,
                tenant_id=tenant_id,
                client_id=client_id,
            )
            return EngineResult.failure(
                ENGINE_ID,
                DISPLAY_NAME,
                CAPABILITY_IDS,
                tenant_id,
                client_id,
                correlation_id,
                causation_id,
                actor,
                owning_role_id,
                input_payload,
                "unauthorized",
                decision.reason,
                warnings,
                data_classification=data_class,
                data_mode="sample" if is_sample else "real",
                is_sample=is_sample,
                duration_ms=int((time.time() - start) * 1000),
            )
    except Exception as e:
        if "unauthorized" in str(e).lower():
            return EngineResult.failure(
                ENGINE_ID,
                DISPLAY_NAME,
                CAPABILITY_IDS,
                tenant_id,
                client_id,
                correlation_id,
                causation_id,
                actor,
                owning_role_id,
                input_payload,
                "unauthorized",
                str(e),
                warnings,
                data_classification=data_class,
                data_mode="sample" if is_sample else "real",
                is_sample=is_sample,
                duration_ms=int((time.time() - start) * 1000),
            )

    # Validate CRM inputs: client/deal/ticket inputs
    try:
        client = input_payload.get("client")
        deal = input_payload.get("deal")
        ticket = input_payload.get("ticket")
        pipeline = input_payload.get("pipeline")

        if client is None and deal is None and ticket is None and pipeline is None:
            if is_sample or input_payload.get("use_sample", False):
                warnings.append("using sample client/deal/ticket data — not live operational data")
                is_sample = True
                client = {"name": "TestClient", "id": "client_123"}
                deal = {"id": "deal_123", "value": 50000, "stage": "proposal"}
                ticket = {"id": "ticket_123", "issue": "Test issue"}
            else:
                raise ValueError("missing required CRM inputs: client/deal/ticket/pipeline")

        if client is not None and not isinstance(client, dict):
            raise ValueError("client must be dict")
        if deal is not None and not isinstance(deal, dict):
            raise ValueError("deal must be dict")
        if ticket is not None and not isinstance(ticket, dict):
            raise ValueError("ticket must be dict")

    except (ValueError, TypeError) as e:
        _audit(
            "crm_validation_failed",
            correlation_id,
            actor,
            decision="denied",
            tenant_id=tenant_id,
            client_id=client_id,
        )
        _log(
            "crm_validation_failed",
            correlation_id,
            actor,
            "failed",
            error_code="invalid_input",
            tenant_id=tenant_id,
            client_id=client_id,
            payload={"error": str(e)},
        )
        return EngineResult.failure(
            ENGINE_ID,
            DISPLAY_NAME,
            CAPABILITY_IDS,
            tenant_id,
            client_id,
            correlation_id,
            causation_id,
            actor,
            owning_role_id,
            input_payload,
            "invalid_input",
            str(e),
            warnings,
            data_classification=data_class,
            data_mode="sample" if is_sample else "real",
            is_sample=is_sample,
            duration_ms=int((time.time() - start) * 1000),
        )

    try:
        from engines.crm.src.sales_pipeline import Deal, Lead, SalesPipeline

        pipe = SalesPipeline()

        # Map the adapter's request input into real engine objects so that
        # get_sales_analytics() computes over data the caller actually supplied
        # (leads and deals), instead of echoing the input back.
        if client is not None:
            lead = Lead(
                lead_id=str(client.get("id", "client_unknown")),
                name=str(client.get("name", "Unknown Client")),
                email=str(client.get("email", "client@example.com")),
                company=str(client.get("company", client.get("name", "Unknown Company"))),
                source=str(client.get("source", "crm_adapter")),
                score=float(client.get("score", 0.0)),
            )
            pipe.add_lead(lead)

        if deal is not None:
            stage = str(deal.get("stage", "proposal"))
            # Deal.probability is a required constructor argument. The CRM request
            # schema carries no probability field, so default it from the engine's
            # own stage config — an explicit, documented default rather than
            # invented business meaning.
            probability = (
                float(deal["probability"])
                if "probability" in deal
                else float(pipe.config["pipeline_stages"].get(stage, {}).get("probability", 0.5))
            )
            deal_obj = Deal(
                deal_id=str(deal.get("id", "deal_unknown")),
                lead_id=str(client.get("id", "client_unknown"))
                if client is not None
                else "lead_unknown",
                title=str(deal.get("title", f"Deal {deal.get('id', 'unknown')}")),
                value=float(deal.get("value", 0.0)),
                stage=stage,
                probability=probability,
                close_date=deal.get("close_date"),
            )
            pipe.create_deal(deal_obj)

        # score_lead is intentionally NOT called. Its signature requires
        # company_size, industry, budget, and timeline business attributes that the
        # CRM request schema does not carry. Scoring a lead from fabricated
        # attributes would re-introduce the same invented-metrics defect this fix
        # removes. The pipeline-analytics request type is about deal/lead
        # distribution and value, not lead scoring.
        metrics = pipe.get_sales_analytics()

        # Keep the consumer-facing pipeline_status flag (asserted by
        # tests/test_c5_vertical_slice.py); derive it from real data rather than
        # hardcoding it.
        metrics["pipeline_status"] = (
            "active"
            if (metrics.get("total_deals", 0) + metrics.get("total_leads", 0)) > 0
            else "empty"
        )
        # For client-confidential/financial, ensure warnings
        if data_class == DataClassification.FINANCIAL:
            warnings.append("financial data — handled as client_confidential/financial")

        if is_sample:
            warnings.append("sample/demo data — not live operational data")

        duration = int((time.time() - start) * 1000)
        evidence = [{"type": "engine_output", "engine": ENGINE_ID, "capability": CAPABILITY_IDS[0]}]
        _audit(
            "crm_executed",
            correlation_id,
            actor,
            decision="succeeded",
            tenant_id=tenant_id,
            client_id=client_id,
        )
        _log(
            "crm_executed",
            correlation_id,
            actor,
            "succeeded",
            tenant_id=tenant_id,
            client_id=client_id,
            capability=CAPABILITY_IDS[0],
            tool="crm_engine",
            duration_ms=duration,
        )

        recommendations = [
            {
                "type": "crm",
                "value": metrics.get("pipeline_status", "active"),
                "source": "calculated",
            }
        ]

        return EngineResult.success(
            ENGINE_ID,
            DISPLAY_NAME,
            CAPABILITY_IDS,
            tenant_id,
            client_id,
            correlation_id,
            causation_id,
            actor,
            owning_role_id,
            metrics,
            input_payload,
            recommendations=recommendations,
            evidence=evidence,
            warnings=warnings,
            data_classification=data_class,
            data_mode="sample" if is_sample else "real",
            is_sample=is_sample,
            duration_ms=duration,
        )

    except Exception as e:
        code = "dependency_unavailable" if "No module" in str(e) else "engine_error"
        _audit(
            "crm_failed",
            correlation_id,
            actor,
            decision="failed",
            tenant_id=tenant_id,
            client_id=client_id,
        )
        _log(
            "crm_failed",
            correlation_id,
            actor,
            "failed",
            error_code=code,
            tenant_id=tenant_id,
            client_id=client_id,
            payload={"error": str(e)},
        )
        return EngineResult.failure(
            ENGINE_ID,
            DISPLAY_NAME,
            CAPABILITY_IDS,
            tenant_id,
            client_id,
            correlation_id,
            causation_id,
            actor,
            owning_role_id,
            input_payload,
            code,
            str(e),
            warnings,
            data_classification=data_class,
            data_mode="sample" if is_sample else "real",
            is_sample=is_sample,
            duration_ms=int((time.time() - start) * 1000),
        )
