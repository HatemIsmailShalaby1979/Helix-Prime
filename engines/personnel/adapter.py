"""
Personnel Engine — Adapter (C4)
Invokes actual engines/personnel/src/main.py etc.
Personnel-sensitive classification.
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

ENGINE_ID = "personnel"
DISPLAY_NAME = "Personnel Engine"
CAPABILITY_IDS = ["talent_acquisition", "workforce_planning", "hiring_pipeline"]
OWNING_ROLE = "hr_personnel_gm"
DATA_CLASSIFICATION = DataClassification.PERSONNEL_SENSITIVE


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
            tool="personnel_engine",
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
            "personnel_policy_denied",
            correlation_id,
            actor,
            decision="denied",
            tenant_id=tenant_id,
            client_id=client_id,
        )
        _log(
            "personnel_policy_denied",
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
    try:
        validate_payload_classification(input_payload, data_class)
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

    # Enforce personnel-sensitive requires correct classification
    if data_class != DataClassification.PERSONNEL_SENSITIVE and not is_sample:
        # For C4, we allow internal but warn if personnel data is being handled as internal
        if "candidate" in str(input_payload).lower() or "workforce" in str(input_payload).lower():
            warnings.append(
                f"personnel data should be {DataClassification.PERSONNEL_SENSITIVE}, got {data_class}"
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
                capability="talent_acquisition",
                tool="personnel_engine",
                owning_role_id=OWNING_ROLE,
                target_tenant_id=tenant_id,
                target_client_id=client_id,
            )
        )
        if not decision.allowed:
            _audit(
                "personnel_authorization_denied",
                correlation_id,
                actor,
                decision="denied",
                tenant_id=tenant_id,
                client_id=client_id,
            )
            _log(
                "personnel_authorization_denied",
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

    # Validate personnel inputs: candidate/workforce inputs
    try:
        candidate = input_payload.get("candidate")
        workforce = input_payload.get("workforce")
        pipeline = input_payload.get("pipeline")

        if candidate is None and workforce is None and pipeline is None:
            if is_sample or input_payload.get("use_sample", False):
                warnings.append("using sample candidate/workforce data — not live operational data")
                is_sample = True
                candidate = {"name": "Alice Smith", "role": "Agent", "skills": ["CS", "Sales"]}
                workforce = {"headcount": 100, "open_positions": 5}
            else:
                raise ValueError("missing required personnel inputs: candidate/workforce/pipeline")

        if candidate is not None and not isinstance(candidate, dict):
            raise ValueError("candidate must be dict")
        if workforce is not None and not isinstance(workforce, dict):
            raise ValueError("workforce must be dict")

    except (ValueError, TypeError) as e:
        _audit(
            "personnel_validation_failed",
            correlation_id,
            actor,
            decision="denied",
            tenant_id=tenant_id,
            client_id=client_id,
        )
        _log(
            "personnel_validation_failed",
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
        from engines.personnel.src.pipeline_manager import Candidate, JobPosting, PipelineManager

        mgr = PipelineManager()

        # Populate the manager with real engine objects BEFORE computing analytics,
        # so get_pipeline_analytics() runs over data the caller actually supplied
        # (previously the analytics ran first on an empty manager, then the raw
        # candidate dict was passed to add_candidate and failed silently).
        if candidate is not None:
            cand = Candidate(
                candidate_id=str(
                    candidate.get("id", candidate.get("candidate_id", "cand_unknown"))
                ),
                name=str(candidate.get("name", "Unknown Candidate")),
                email=str(candidate.get("email", "candidate@example.com")),
                position=str(candidate.get("position", candidate.get("role", "Unknown Position"))),
                experience=int(candidate.get("experience", 0)),
                skills=list(candidate.get("skills", [])),
                score=float(candidate.get("score", 0.0)),
            )
            mgr.add_candidate(cand)

        job_id = None
        if workforce is not None:
            # The workforce payload describes hiring demand; model it as a real
            # JobPosting. Required fields the request does not supply are defaulted
            # explicitly to a neutral "Open Position", not invented as business
            # meaning.
            job_id = str(workforce.get("job_id", workforce.get("id", "job_workforce")))
            job = JobPosting(
                job_id=job_id,
                title=str(workforce.get("title", "Open Position")),
                department=str(workforce.get("department", "General")),
                required_skills=list(workforce.get("required_skills", [])),
                experience_level=int(workforce.get("experience_level", 0)),
                salary_range=dict(workforce.get("salary_range", {"min": 0.0, "max": 0.0})),
                deadline=str(workforce.get("deadline", "2099-12-31")),
            )
            mgr.create_job_posting(job)

        # Screen candidates against the posting only when the input actually
        # supports a meaningful screen (job-like fields present).
        if (
            job_id is not None
            and workforce.get("required_skills")
            and int(workforce.get("experience_level", 0)) > 0
        ):
            try:
                mgr.screen_candidates(job_id)
            except Exception:
                pass

        # Compute analytics over the populated manager — real, not empty.
        analytics = mgr.get_pipeline_analytics()
        metrics = analytics

        # pipeline_status is derived from the real pipeline state, not hardcoded.
        metrics["pipeline_status"] = (
            "active"
            if (metrics.get("total_candidates", 0) + metrics.get("total_job_postings", 0)) > 0
            else "empty"
        )
        # Surface real job-posting detail when a posting was created.
        if job_id is not None:
            metrics["job_posting_status"] = mgr.get_job_posting_status(job_id)
        # NOTE: the previously hardcoded `workforce_headcount` (echoed from the
        # request input) is dropped — PipelineManager models candidates and job
        # postings, not an existing workforce headcount, so no real headcount can be
        # sourced. The real computed totals (total_candidates, total_job_postings,
        # job_posting_status) are the honest workforce-related figures.

        # Distinguish calculated vs recommended — derive from real counts, not the
        # old hardcoded open_positions default of 5.
        recommendations = [
            {
                "type": "hiring",
                "value": metrics.get("total_job_postings", 0),
                "source": "calculated",
            }
        ]

        if is_sample:
            warnings.append("sample/demo data — not live operational data")

        duration = int((time.time() - start) * 1000)
        evidence = [{"type": "engine_output", "engine": ENGINE_ID, "capability": CAPABILITY_IDS[0]}]
        _audit(
            "personnel_executed",
            correlation_id,
            actor,
            decision="succeeded",
            tenant_id=tenant_id,
            client_id=client_id,
        )
        _log(
            "personnel_executed",
            correlation_id,
            actor,
            "succeeded",
            tenant_id=tenant_id,
            client_id=client_id,
            capability=CAPABILITY_IDS[0],
            tool="personnel_engine",
            duration_ms=duration,
        )

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
            "personnel_failed",
            correlation_id,
            actor,
            decision="failed",
            tenant_id=tenant_id,
            client_id=client_id,
        )
        _log(
            "personnel_failed",
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
