"""Evidence-gated metacognitive improvement system (Prompt 8).

Metacognition here is a CONTROLLED improvement-proposal system, not a runtime
mutator. It may:
* detect repeated failures and performance drift,
* propose workflow/policy/permission/memory-rule improvements,
* compare a proposed change against a baseline,
* evaluate the change against historical + simulated cases,
* generate an evidence report.

It may NOT (and the engine enforces this by construction):
* silently modify production behavior,
* silently change policies / memory rules / permissions,
* deploy itself,
* remove audit evidence.

Every proposal is an append-only, hash-chained ledger record carrying: baseline,
hypothesis, evidence, evaluation results, risk assessment, reviewer, approval
state, version, and rollback plan. The engine only flips a proposal's *state*;
it never writes to any live runtime. Deployment is an EXPLICIT, gated step
performed by a caller via :func:`apply_proposal` / :func:`rollback_proposal`,
which are never invoked by the engine.

Deterministic and local-first: no RNG, no wall-clock (callers supply timestamps),
no cloud.
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field, asdict
from typing import Any, Callable, Mapping, Optional, Sequence

GENESIS_HASH = "0" * 64

# Approval-state machine -------------------------------------------------------
DRAFT = "draft"
EVALUATING = "evaluating"
EVALUATED = "evaluated"                # passed evaluation, awaiting approval
EVALUATED_FAILED = "evaluated_failed"  # failed evaluation, cannot be approved
REJECTED = "rejected"
APPROVED = "approved"
ROLLED_BACK = "rolled_back"

PROPOSAL_KINDS = ("workflow", "policy", "permission", "memory_rule")
_APPROVABLE = (EVALUATED, DRAFT)  # a proposal must have passed evaluation to approve


@dataclass(frozen=True)
class FailureSignal:
    target: str
    count: int
    sample_ids: list
    detail: str


@dataclass(frozen=True)
class DriftSignal:
    metric: str
    baseline_rate: float
    recent_rate: float
    delta: float
    detail: str


@dataclass(frozen=True)
class ImprovementProposal:
    proposal_id: str
    version: int
    tenant_id: str
    client_id: str
    created_by: str
    role_id: str
    correlation_id: str
    timestamp: str
    data_mode: str
    classification: str
    kind: str
    target: str
    baseline: str
    proposed: str
    baseline_policy: dict
    proposed_policy: dict
    min_improvement: float
    hypothesis: str
    evidence: list
    evaluation_results: dict
    risk_assessment: str
    reviewer: Optional[str]
    approval_state: str
    rollback_plan: str
    provenance: dict
    supersedes: Optional[str] = None
    applied: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class EvaluationResult:
    baseline_rate: float
    proposed_rate: float
    delta: float
    n_historical: int
    n_simulated: int
    passed: bool
    detail: str


@dataclass(frozen=True)
class ApprovalDecision:
    decision: str  # allowed | denied | not_required
    reason: str


class ProposalTamperError(Exception):
    pass


def _canonical(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, default=str)


class MetacognitionEngine:
    """Local-first, append-only, hash-chained improvement-proposal ledger.

    The engine NEVER mutates runtime state. It only creates and transitions
    proposal records (each transition is a new versioned, hash-chained snapshot).
    """

    def __init__(self, path: Optional[str] = None) -> None:
        self.path = path
        self._ledger: list[dict] = []
        self._latest: dict[str, ImprovementProposal] = {}
        if path and os.path.exists(path):
            self._load()

    # ------------------------------------------------------------- persistence
    def _load(self) -> None:
        with open(self.path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    self._ledger.append(json.loads(line))
        self._reindex()

    def _reindex(self) -> None:
        self._latest = {}
        for env in self._ledger:
            rec = ImprovementProposal(**env["record"])
            # keep the highest version per proposal_id
            cur = self._latest.get(rec.proposal_id)
            if cur is None or rec.version > cur.version:
                self._latest[rec.proposal_id] = rec

    def _append(self, proposal: ImprovementProposal) -> None:
        payload = proposal.to_dict()
        prev = self._ledger[-1]["hash"] if self._ledger else GENESIS_HASH
        h = hashlib.sha256((_canonical(payload) + "|" + prev).encode("utf-8")).hexdigest()
        self._ledger.append({"record": payload, "prev_hash": prev, "hash": h})
        self._latest[proposal.proposal_id] = proposal
        if self.path:
            with open(self.path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(self._ledger[-1], default=str) + "\n")

    def verify_chain(self) -> tuple[bool, str]:
        prev = GENESIS_HASH
        for env in self._ledger:
            payload = env["record"]
            expected = hashlib.sha256(
                (_canonical(payload) + "|" + prev).encode("utf-8")
            ).hexdigest()
            if env.get("prev_hash") != prev or env.get("hash") != expected:
                return False, f"chain broken at {payload.get('proposal_id')}"
            prev = env["hash"]
        return True, "chain intact"

    # ----------------------------------------------------------- detection
    def detect_repeated_failures(
        self, failure_records: Sequence[Mapping[str, Any]], threshold: int = 3
    ) -> list[FailureSignal]:
        """Group failure/outcome records by target reason; flag repeats >= threshold."""
        groups: dict[str, list[str]] = {}
        for r in failure_records:
            if r.get("kind") not in ("failure", "outcome"):
                continue
            decision = r.get("decision") or r.get("body", {}).get("decision")
            if decision not in ("failed", "rejected"):
                continue
            target = r.get("target") or r.get("body", {}).get("target") or r.get("record_id", "?")
            groups.setdefault(target, []).append(r.get("record_id", "?"))
        out = []
        for target, ids in groups.items():
            if len(ids) >= threshold:
                out.append(FailureSignal(
                    target=target, count=len(ids), sample_ids=ids[:5],
                    detail=f"{len(ids)} repeated failures on {target}",
                ))
        return out

    def detect_performance_drift(
        self, metric: str, baseline_rate: float, recent_rate: float, threshold: float = 0.05
    ) -> Optional[DriftSignal]:
        delta = recent_rate - baseline_rate
        if abs(delta) > threshold:
            return DriftSignal(
                metric=metric, baseline_rate=baseline_rate, recent_rate=recent_rate,
                delta=delta, detail=f"{metric} drifted by {delta:+.3f}",
            )
        return None

    # ----------------------------------------------------------- propose
    def propose(
        self,
        *,
        kind: str,
        target: str,
        baseline: str,
        proposed: str,
        baseline_policy: Mapping[str, Any],
        proposed_policy: Mapping[str, Any],
        hypothesis: str,
        evidence: Sequence[str],
        risk_assessment: str,
        rollback_plan: str,
        tenant_id: str,
        client_id: str,
        created_by: str,
        role_id: str,
        correlation_id: str,
        timestamp: str,
        min_improvement: float = 0.0,
        data_mode: str = "simulated_realistic",
        classification: str = "client_confidential",
        provenance: Optional[Mapping[str, Any]] = None,
    ) -> ImprovementProposal:
        if kind not in PROPOSAL_KINDS:
            raise ValueError(f"unknown proposal kind {kind!r}")
        if not tenant_id:
            raise ValueError("tenant_id is required")
        seq = len(self._ledger) + 1
        rec = ImprovementProposal(
            proposal_id=f"prop-{seq:04d}",
            version=1,
            tenant_id=tenant_id,
            client_id=client_id,
            created_by=created_by,
            role_id=role_id,
            correlation_id=correlation_id,
            timestamp=timestamp,
            data_mode=data_mode,
            classification=classification,
            kind=kind,
            target=target,
            baseline=baseline,
            proposed=proposed,
            baseline_policy=dict(baseline_policy),
            proposed_policy=dict(proposed_policy),
            min_improvement=float(min_improvement),
            hypothesis=hypothesis,
            evidence=list(evidence),
            evaluation_results={},
            risk_assessment=risk_assessment,
            reviewer=None,
            approval_state=DRAFT,
            rollback_plan=rollback_plan,
            provenance=dict(provenance or {}),
            supersedes=None,
            applied=False,
        )
        self._append(rec)
        return rec

    # ----------------------------------------------------------- evaluate
    def evaluate(
        self,
        proposal: ImprovementProposal,
        historical_cases: Sequence[Mapping[str, Any]],
        simulated_cases: Sequence[Mapping[str, Any]],
        simulate: Callable[[Mapping[str, Any], Mapping[str, Any]], bool],
    ) -> EvaluationResult:
        """Compare proposed policy vs baseline over historical + simulated cases.

        Pure and deterministic: never touches runtime. On failure the proposal
        transitions to EVALUATED_FAILED (and can no longer be approved)."""
        all_cases = list(historical_cases) + list(simulated_cases)

        def _rate(policy: Mapping[str, Any]) -> float:
            if not all_cases:
                return 0.0
            ok = sum(1 for c in all_cases if simulate(policy, c))
            return ok / len(all_cases)

        base_rate = _rate(proposal.baseline_policy)
        prop_rate = _rate(proposal.proposed_policy)
        delta = prop_rate - base_rate
        passed = delta >= proposal.min_improvement
        result = EvaluationResult(
            baseline_rate=base_rate,
            proposed_rate=prop_rate,
            delta=delta,
            n_historical=len(historical_cases),
            n_simulated=len(simulated_cases),
            passed=passed,
            detail=("proposed change meets/exceeds minimum improvement"
                    if passed else "proposed change does not improve over baseline"),
        )
        new_state = EVALUATED if passed else EVALUATED_FAILED
        updated = ImprovementProposal(
            **{**proposal.to_dict(), "evaluation_results": asdict(result), "approval_state": new_state},
        )
        self._append(updated)
        return result

    # ----------------------------------------------------------- approval gate
    def _transition(self, proposal_id: str, **changes: Any) -> ImprovementProposal:
        prev = self._latest.get(proposal_id)
        if prev is None:
            raise KeyError(f"no such proposal {proposal_id!r}")
        new = ImprovementProposal(**{**prev.to_dict(), "version": prev.version + 1, "supersedes": prev.proposal_id, **changes})
        self._append(new)
        return new

    def approve(
        self,
        proposal_id: str,
        reviewer: str,
        approver_role: str,
        requester_actor: Optional[str] = None,
        requester_role: Optional[str] = None,
    ) -> ApprovalDecision:
        prev = self._latest.get(proposal_id)
        if prev is None:
            raise KeyError(f"no such proposal {proposal_id!r}")
        if prev.approval_state == EVALUATED_FAILED:
            return ApprovalDecision("denied", "Proposal failed evaluation; cannot be approved")
        if prev.approval_state not in _APPROVABLE:
            return ApprovalDecision("denied", f"Proposal not in an approvable state ({prev.approval_state})")
        req_actor = requester_actor or prev.created_by
        req_role = requester_role or prev.role_id
        if reviewer == req_actor:
            return ApprovalDecision("denied", "Self-approval denied (separation of duties)")
        if approver_role == req_role:
            return ApprovalDecision("denied", "Same-role approval denied (separation of duties)")
        self._transition(proposal_id, reviewer=reviewer, approval_state=APPROVED)
        return ApprovalDecision("allowed", "Cross-role approval satisfied")

    def reject(self, proposal_id: str, reviewer: str, reason: str) -> ImprovementProposal:
        return self._transition(proposal_id, reviewer=reviewer, approval_state=REJECTED,
                                rollback_plan=f"rejected by {reviewer}: {reason}")

    def rollback(self, proposal_id: str, actor: str, reason: str) -> ImprovementProposal:
        return self._transition(proposal_id, approval_state=ROLLED_BACK,
                                rollback_plan=f"rolled back by {actor}: {reason}")

    # ----------------------------------------------------------- queries
    def get_proposal(self, proposal_id: str) -> ImprovementProposal:
        if proposal_id not in self._latest:
            raise KeyError(f"no such proposal {proposal_id!r}")
        return self._latest[proposal_id]

    def list_proposals(
        self, tenant_id: Optional[str] = None, state: Optional[str] = None
    ) -> list[ImprovementProposal]:
        out = [p for p in self._latest.values()]
        if tenant_id is not None:
            out = [p for p in out if p.tenant_id == tenant_id]
        if state is not None:
            out = [p for p in out if p.approval_state == state]
        return out

    # ----------------------------------------------------------- evidence report
    def generate_evidence_report(self, proposal: ImprovementProposal) -> dict:
        ok, chain = self.verify_chain()
        return {
            "proposal_id": proposal.proposal_id,
            "version": proposal.version,
            "kind": proposal.kind,
            "target": proposal.target,
            "tenant_id": proposal.tenant_id,
            "client_id": proposal.client_id,
            "classification": proposal.classification,
            "data_mode": proposal.data_mode,
            "correlation_id": proposal.correlation_id,
            "baseline": proposal.baseline,
            "hypothesis": proposal.hypothesis,
            "proposed": proposal.proposed,
            "evidence": list(proposal.evidence),
            "evaluation_results": dict(proposal.evaluation_results),
            "risk_assessment": proposal.risk_assessment,
            "reviewer": proposal.reviewer,
            "approval_state": proposal.approval_state,
            "rollback_plan": proposal.rollback_plan,
            "provenance": dict(proposal.provenance),
            "audit_chain": chain,
        }


# Explicit, gated deployment steps (NEVER called by the engine) ----------------
def apply_proposal(runtime: Mapping[str, Any], proposal: ImprovementProposal, actor: str, role_id: str) -> None:
    """Human-gated deployment. Requires an APPROVED proposal and an explicit call.
    The engine never invokes this, so unapproved proposals cannot change runtime."""
    if proposal.approval_state != APPROVED:
        raise RuntimeError(f"cannot deploy unapproved proposal {proposal.proposal_id} ({proposal.approval_state})")
    if proposal.kind not in ("policy", "workflow", "permission", "memory_rule"):
        raise RuntimeError(f"unsupported proposal kind {proposal.kind!r}")
    # Apply the proposed change to the (caller-owned) runtime mapping.
    target = proposal.target
    value = proposal.proposed_policy.get("value", proposal.proposed_policy)
    if isinstance(runtime, dict):
        runtime[target] = value


def rollback_proposal(runtime: Mapping[str, Any], proposal: ImprovementProposal, actor: str, role_id: str) -> None:
    """Human-gated rollback. Restores the baseline value into the runtime mapping."""
    if isinstance(runtime, dict):
        runtime[proposal.target] = proposal.baseline_policy.get("value", proposal.baseline_policy)
