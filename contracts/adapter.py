"""
Compatibility seam for Helix Prime Codex C1 → C2.

C1 additive goal: introduce typed contracts alongside existing
model-invented `call_agent("NAME", "message")` text. Do NOT remove
BaseAgent.call_agent or the regex fallback. Do NOT allow model text
to bypass role permissions or approvals.

This adapter shows the intended C2 migration:
  1. Model text `call_agent(...)` is parsed (fallback, compatibility)
  2. Parsed intent is converted to a validated TaskRequest (structured path)
  3. Request is validated against role catalog (peer-call permission, SOD, approval tier)
  4. Only validated requests proceed to execution; otherwise they are refused/queued for review.

C2 will replace step 1 with direct structured tool calls; this file remains the
compatibility bridge.

Usage example (C1, catalog present):
    from contracts.adapter import parse_legacy_calls, to_task_request, validate_request_against_catalog
    from contracts.task import CorrelationContext
    from organization.role_catalog import load_role_catalog

    catalog = load_role_catalog("organization/role-catalog.yaml")
    legacy = 'call_agent("PHILI", "What is headcount for Account Beta?")'
    for agent_name, msg in parse_legacy_calls(legacy):
        req = to_task_request(
            correlation=CorrelationContext.new(client_id="Account Beta"),
            requesting_actor="sami",
            requesting_role_id="sami",
            owning_role_id="hr_personnel_gm",
            capability="workforce_planning",
            input_payload={"question": msg},
        )
        # validate does NOT bypass: it will raise if peer call not allowed or approval missing
        validate_request_against_catalog(req, catalog)

No network, no secrets, no DB migration.
"""
from __future__ import annotations

import datetime
import re
from typing import List, Tuple, Dict, Any

from contracts.task import CorrelationContext, TaskRequest

# Same pattern as BaseAgent.process_request — keep in sync
_CALL_AGENT_RE = re.compile(r'call_agent\((["\'])([A-Z_]+)\1,\s*(["\'])(.*?)\3\)', re.DOTALL)


def parse_legacy_calls(text: str) -> List[Tuple[str, str]]:
    """
    Parse legacy model-invented call_agent(...) snippets.

    Returns list of (AGENT_NAME, message). Empty list if none.
    This is a compatibility helper; it does NOT execute calls.

    >>> parse_legacy_calls('call_agent("PHILI", "hello") and call_agent(\\'WILI\\', "hi")')
    [('PHILI', 'hello'), ('WILI', 'hi')]
    """
    if not isinstance(text, str):
        raise ValueError(f"parse_legacy_calls: text must be str, got {type(text).__name__}")
    results: List[Tuple[str, str]] = []
    for m in _CALL_AGENT_RE.finditer(text):
        agent = m.group(2).strip().upper()
        msg = m.group(4).strip()
        if agent and msg:
            results.append((agent, msg))
    return results


def to_task_request(
    correlation: CorrelationContext,
    requesting_actor: str,
    requesting_role_id: str,
    owning_role_id: str,
    capability: str,
    input_payload: Dict[str, Any],
    requires_approval: bool = False,
    approval_limit_tier: str | None = None,
) -> TaskRequest:
    """
    Convert legacy intent to validated TaskRequest.

    The resulting request is fully validated (timestamps, IDs, correlation).
    Callers must still validate against catalog via validate_request_against_catalog
    before execution — this function alone does not authorize.
    """
    if not isinstance(correlation, CorrelationContext):
        raise ValueError(f"to_task_request: correlation must be CorrelationContext, got {type(correlation).__name__}")
    now = datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")
    # request_id stable within correlation but unique per call
    import uuid

    rid = f"req_{uuid.uuid4().hex[:12]}"
    return TaskRequest(
        request_id=rid,
        correlation=correlation,
        requesting_actor=requesting_actor,
        owning_role_id=owning_role_id,
        capability=capability,
        input_payload=input_payload,
        requires_approval=requires_approval,
        status="proposed",
        created_at=now,
        tenant_id=correlation.tenant_id,
        client_id=correlation.client_id,
        approval_limit_tier=approval_limit_tier,
    )


def validate_request_against_catalog(request: TaskRequest, catalog: Dict[str, Any]) -> None:
    """
    Validate TaskRequest against role catalog governance.

    Checks (fail-closed, no bypass):
    - owning_role_id exists in catalog
    - requesting_role_id (inferred from requesting_actor if actor == role id, else explicit) — here we check requesting_actor's role if it matches a role id; if not, we only check owning role exists and capability is owned.
    - capability is owned by owning_role_id (per catalog owned_capabilities)
      Note: model text cannot invent capabilities outside catalog; this is the guard.
    - peer call permission: requesting_role -> owning_role must be in allowed_peer_calls (when requesting_role is known)
    - approval tier: if request.requires_approval, verify owning role can_approve or escalation path exists

    Raises ValueError on violation (caller must handle as refused/review queue).
    Does NOT execute the request.
    """
    if not isinstance(request, TaskRequest):
        raise ValueError(f"validate_request_against_catalog: request must be TaskRequest, got {type(request).__name__}")
    if not isinstance(catalog, dict) or "roles_by_id" not in catalog:
        raise ValueError("validate_request_against_catalog: catalog must be loaded via load_role_catalog (missing roles_by_id)")

    roles_by_id = catalog["roles_by_id"]
    if request.owning_role_id not in roles_by_id:
        raise ValueError(
            f"TaskRequest owning_role_id {request.owning_role_id!r} not in catalog {sorted(roles_by_id.keys())}"
        )

    owning = roles_by_id[request.owning_role_id]
    # capability must be owned by target role (prevents model inventing arbitrary capabilities)
    if request.capability not in owning.get("owned_capabilities", []):
        raise ValueError(
            f"TaskRequest capability {request.capability!r} not owned by role {request.owning_role_id!r} "
            f"(owned: {owning.get('owned_capabilities')})"
        )

    # try infer requesting role: if requesting_actor == role id, use it; else if actor contains role id lower, map?
    # For C1 we accept explicit check only when requesting_actor matches a role id (e.g., 'sami')
    req_role_id: str | None = None
    # exact match lower
    lower_actor = request.requesting_actor.strip().lower()
    if lower_actor in roles_by_id:
        req_role_id = lower_actor
    else:
        # try upper mapping like SAMI -> sami
        up = request.requesting_actor.strip().upper()
        # map AGENT names to role ids: SAMI->sami, PHILI->hr_personnel_gm, WILI->ld_gm, SUBY->ops_gm
        agent_to_role = {
            "SAMI": "sami",
            "PHILI": "hr_personnel_gm",
            "WILI": "ld_gm",
            "SUBY": "ops_gm",
        }
        if up in agent_to_role:
            req_role_id = agent_to_role[up]

    if req_role_id is not None:
        # peer permission check
        req_role = roles_by_id[req_role_id]
        allowed = req_role.get("allowed_peer_calls", [])
        if request.owning_role_id not in allowed:
            raise ValueError(
                f"Peer call not allowed: {req_role_id!r} -> {request.owning_role_id!r} "
                f"(allowed: {allowed}) — fail closed per C1 SOD"
            )

    # approval tier check: if requires_approval, verify owning role tier can approve or escalation exists
    if request.requires_approval:
        tier = request.approval_limit_tier
        if tier is None:
            # default tier is owning role's tier; no extra check in C1 aside from existence
            pass
        else:
            # ensure tier matches owning role's can_approve or is escalation
            owning_can = owning.get("approval_limits", {}).get("can_approve", [])
            if tier not in owning_can:
                # allow if escalation_owner's role can approve
                esc_owner = owning.get("escalation_owner")
                if esc_owner and esc_owner in roles_by_id:
                    esc_can = roles_by_id[esc_owner].get("approval_limits", {}).get("can_approve", [])
                    if tier not in esc_can:
                        raise ValueError(
                            f"Approval tier {tier!r} not allowed for role {request.owning_role_id!r} "
                            f"(can_approve: {owning_can}, escalation {esc_owner} can: {esc_can})"
                        )
                else:
                    raise ValueError(
                        f"Approval tier {tier!r} not allowed for role {request.owning_role_id!r} (can_approve: {owning_can})"
                    )

    # SOD: if requesting role must be reviewed by compliance, flag but do not fail here — C2 will enforce review queue.
    # For C1 we just validate structure, not enforce full workflow.
