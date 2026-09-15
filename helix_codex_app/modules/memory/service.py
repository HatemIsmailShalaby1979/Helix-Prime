"""The memory lifecycle: propose, evaluate, review, roll back.

A proposal lives in its author's own ledger. The author is the only one who may
evaluate it, and the reviewer reaches it through the tenant-scoped projection —
never by being handed somebody else's ledger. That is why every write path here
resolves the *owner* of the proposal first and works in the owner's ledger, with
the acting account recorded separately as the actor.

The ledger is the source of truth; the projection is refreshed from it after
every transition. Separation of duties is delegated to the metacognition engine
and surfaced here as a typed refusal, so a reviewer can never approve their own
proposal, and a proposal that has not passed evaluation can never be approved.

Evaluation is deterministic and local. It scores the baseline policy and the
proposed policy over the author's own memory records, using each record's
confidence as the case score. That is a real comparison over real evidence, but a
modest one — a richer case source is a later step, and this docstring says so
rather than letting the screen imply otherwise.
"""
from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Mapping, Sequence

from helix_codex_app import db
from helix_codex_app.db import record_node
from helix_codex_app.errors import InvalidStateError, NotFoundError, PermissionDenied
from helix_codex_app.integration.memory_bridge import AccountMemoryStore
from helix_codex_app.integration.metacognition_bridge import AccountMetacognition
from helix_codex_app.modules.memory.repository import MemoryRepository, ProposalRow
from helix_codex_app.security.accounts import Account, AccountRepository
from metacognition.improvement import (
    ApprovalDecision,
    EvaluationResult,
    ImprovementProposal,
    ProposalNotApprovableError,
    ProposalStateError,
)

PROVENANCE_SOURCE = "helix_codex_app.memory"
PROVENANCE_DATA_MODE = "app_runtime"
CASE_POLICY_KEY = "value"
MAX_EVIDENCE_CASES = 200
ROLLBACK_STATES = ("approved", "rolled_back")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def default_simulate(policy: Mapping[str, Any], case: Mapping[str, Any]) -> bool:
    """The deterministic stand-in used when a caller supplies no simulator.

    A case passes when its score meets the policy's threshold. Both sides come
    from the caller's own proposal and records, so the comparison is honest even
    though the model is simple.
    """
    return float(case.get("score", 0.0)) >= float(policy.get(CASE_POLICY_KEY, 0.0))


def cases_from_memory(records: Sequence[Any]) -> list[dict[str, Any]]:
    """Turn memory records into evaluation cases."""
    return [
        {"record_id": record.record_id, "score": float(record.confidence)}
        for record in records
        if record.confidence is not None
    ]


class MemoryService:
    """Proposals, evaluations, reviews, and rollback for one account's memory."""

    def __init__(self, conn: sqlite3.Connection, *, memory_root: str | None = None) -> None:
        self.conn = conn
        self.repo = MemoryRepository(conn)
        self.accounts = AccountRepository(conn)
        self.engines = AccountMetacognition(memory_root=memory_root)
        self.stores = AccountMemoryStore(conn=conn, memory_root=memory_root)

    # ---------------------------------------------------------------- writes
    def propose(
        self,
        account: Account,
        *,
        kind: str,
        target: str,
        baseline: str,
        proposed: str,
        baseline_policy: Mapping[str, Any],
        proposed_policy: Mapping[str, Any],
        hypothesis: str,
        risk_assessment: str,
        rollback_plan: str,
        evidence: Sequence[str] | None = None,
        min_improvement: float = 0.0,
        correlation_id: str = "",
    ) -> ImprovementProposal:
        """Record a new proposal in the author's own ledger."""
        proposal = self.engines.propose(
            account,
            kind=kind,
            target=target,
            baseline=baseline,
            proposed=proposed,
            baseline_policy=dict(baseline_policy),
            proposed_policy=dict(proposed_policy),
            hypothesis=hypothesis,
            evidence=list(evidence or []),
            risk_assessment=risk_assessment,
            rollback_plan=rollback_plan,
            tenant_id=account.tenant_id,
            client_id=account.client_id or "",
            created_by=account.account_id,
            role_id=account.role_id or "",
            correlation_id=correlation_id or f"corr-{uuid.uuid4().hex}",
            timestamp=_now(),
            min_improvement=min_improvement,
        )
        self._sync(account, proposal, actor_id=account.account_id)
        return proposal

    def evaluate(
        self,
        account: Account,
        proposal_id: str,
        *,
        historical_cases: Sequence[Mapping[str, Any]] | None = None,
        simulated_cases: Sequence[Mapping[str, Any]] | None = None,
        simulate: Callable[[Mapping[str, Any], Mapping[str, Any]], bool] | None = None,
    ) -> EvaluationResult:
        """Score the proposed policy against the baseline over real cases.

        Only the author may evaluate their own proposal. With no cases supplied,
        the author's own memory records are the evidence set.
        """
        owner = self._owner_of(account, proposal_id)
        if owner.account_id != account.account_id:
            raise PermissionDenied(
                "only the author may evaluate this proposal",
                payload={"proposal_id": proposal_id},
            )
        proposal = self.get_proposal(account, proposal_id)
        if historical_cases is None and simulated_cases is None:
            records = self.stores.read(owner, limit=MAX_EVIDENCE_CASES)
            historical_cases = cases_from_memory(records)
            simulated_cases = []
        try:
            result = self.engines.evaluate(
                owner,
                proposal,
                historical_cases=list(historical_cases or []),
                simulated_cases=list(simulated_cases or []),
                simulate=simulate or default_simulate,
            )
        except ProposalStateError as exc:
            raise InvalidStateError(str(exc), payload={"proposal_id": proposal_id}) from exc
        self._sync(owner, self.engines.get(owner, proposal_id), actor_id=account.account_id)
        return result

    def approve(
        self, account: Account, proposal_id: str, *, reason: str = ""
    ) -> ImprovementProposal:
        """Approve a proposal. Separation of duties is the engine's call."""
        owner = self._owner_of(account, proposal_id)
        try:
            decision = self.engines.approve(
                owner,
                proposal_id,
                reviewer=account.account_id,
                approver_role=account.role_id or "",
            )
        except ProposalNotApprovableError as exc:
            raise InvalidStateError(str(exc), payload={"proposal_id": proposal_id}) from exc
        if decision.decision != "allowed":
            self._review(account, proposal_id, decision, reason)
            raise PermissionDenied(
                decision.reason, payload={"proposal_id": proposal_id, "code": decision.decision}
            )
        proposal = self.engines.get(owner, proposal_id)
        self._review(account, proposal_id, decision, reason)
        self._sync(owner, proposal, actor_id=account.account_id)
        return proposal

    def reject(self, account: Account, proposal_id: str, *, reason: str) -> ImprovementProposal:
        """Reject a proposal. A reason is required, and is recorded."""
        if not reason or not reason.strip():
            raise ValueError("a rejection needs a reason")
        owner = self._owner_of(account, proposal_id)
        proposal = self.engines.reject(
            owner, proposal_id, reviewer=account.account_id, reason=reason
        )
        self.repo.insert_review(
            proposal_id=proposal_id,
            reviewer_account_id=account.account_id,
            reviewer_role=account.role_id or "",
            decision="rejected",
            reason=reason,
        )
        self._sync(owner, proposal, actor_id=account.account_id)
        return proposal

    def rollback(self, account: Account, proposal_id: str, *, reason: str) -> ImprovementProposal:
        """Roll a proposal back. Only an applied or approved proposal may be rolled back."""
        owner = self._owner_of(account, proposal_id)
        current = self.engines.get(owner, proposal_id)
        if current.approval_state not in ROLLBACK_STATES:
            raise InvalidStateError(
                f"{proposal_id}: cannot roll back a proposal in state "
                f"{current.approval_state!r}",
                payload={"proposal_id": proposal_id},
            )
        proposal = self.engines.rollback(
            owner, proposal_id, actor=account.account_id, reason=reason or "rolled back"
        )
        self.repo.insert_review(
            proposal_id=proposal_id,
            reviewer_account_id=account.account_id,
            reviewer_role=account.role_id or "",
            decision="rolled_back",
            reason=reason or "rolled back",
        )
        self._sync(owner, proposal, actor_id=account.account_id)
        return proposal

    # ----------------------------------------------------------------- reads
    def get_proposal(self, account: Account, proposal_id: str) -> ImprovementProposal:
        """One proposal from the account's own ledger, or NotFoundError.

        The personal view is own-only: reading somebody else's proposal goes
        through a review path, never through here.
        """
        owner = self._owner_of(account, proposal_id)
        if owner.account_id != account.account_id:
            raise NotFoundError(
                f"no such proposal {proposal_id}", payload={"proposal_id": proposal_id}
            )
        try:
            return self.engines.get(owner, proposal_id)
        except KeyError as exc:
            raise NotFoundError(
                f"no such proposal {proposal_id}", payload={"proposal_id": proposal_id}
            ) from exc

    def list_proposals(self, account: Account, *, state: str | None = None) -> list[ProposalRow]:
        """The account's own proposals, newest first."""
        return self.repo.list_proposals(
            account.tenant_id, state=state, created_by=account.account_id
        )

    def list_reviews(self, proposal_id: str) -> list[sqlite3.Row]:
        return self.repo.list_reviews(proposal_id)

    def evidence_report(self, account: Account, proposal_id: str) -> dict:
        owner = self._owner_of(account, proposal_id)
        if owner.account_id != account.account_id:
            raise NotFoundError(
                f"no such proposal {proposal_id}", payload={"proposal_id": proposal_id}
            )
        return self.engines.evidence_report(owner, self.get_proposal(account, proposal_id))

    def verify_ledger(self, account: Account) -> dict:
        ok, detail = self.engines.verify_chain(account)
        return {
            "ok": ok,
            "detail": detail,
            "store_id": db.store_id_for(path=self.engines.resolve_path(account)),
        }

    # ------------------------------------------------------------ projection
    def rebuild_projection(self, account: Account) -> int:
        """Rebuild the projection from the account's ledger.

        The ledger is the truth. If the projection is ever suspected of drifting,
        this discards it and replays the ledger, so the two cannot stay apart.
        """
        store_id = db.store_id_for(path=self.engines.resolve_path(account))
        self.conn.execute("DELETE FROM proposals WHERE store_id = ?", (store_id,))
        self.conn.commit()
        proposals = self.engines.list(account)
        for proposal in proposals:
            self.repo.upsert_proposal(proposal, store_id=store_id, domain_id=account.domain_id)
        return len(proposals)

    # --------------------------------------------------------------- private
    def _owner_of(self, account: Account, proposal_id: str) -> Account:
        """Resolve a proposal's author through the tenant-scoped projection.

        A proposal is visible only inside its own tenant. A caller outside that
        tenant gets NotFound, the same answer as for a proposal that does not
        exist, so the two are indistinguishable from outside.
        """
        row = self.repo.get_proposal(proposal_id)
        if row is None or row.tenant_id != account.tenant_id:
            raise NotFoundError(
                f"no such proposal {proposal_id}", payload={"proposal_id": proposal_id}
            )
        owner = self.accounts.get_account_by_id(row.created_by)
        if owner is None:
            raise NotFoundError(
                f"no such proposal {proposal_id}", payload={"proposal_id": proposal_id}
            )
        return owner

    def _sync(self, owner: Account, proposal: ImprovementProposal, *, actor_id: str) -> None:
        self.repo.upsert_proposal(
            proposal,
            store_id=db.store_id_for(path=self.engines.resolve_path(owner)),
            domain_id=owner.domain_id,
        )
        self._record_node(owner, proposal, actor_id=actor_id)

    def _review(
        self, account: Account, proposal_id: str, decision: ApprovalDecision, reason: str
    ) -> None:
        self.repo.insert_review(
            proposal_id=proposal_id,
            reviewer_account_id=account.account_id,
            reviewer_role=account.role_id or "",
            decision=decision.decision,
            reason=reason or decision.reason,
        )

    def _record_node(self, owner: Account, proposal: ImprovementProposal, *, actor_id: str) -> None:
        record_node(
            self.conn,
            tenant_id=owner.tenant_id,
            client_id=owner.client_id,
            domain_id=owner.domain_id,
            correlation_id=proposal.correlation_id or f"prop-{proposal.proposal_id}",
            classification=proposal.classification or "client_confidential",
            nature="user_claim",
            created_by=actor_id,
            provenance_source=PROVENANCE_SOURCE,
            provenance_data_mode=PROVENANCE_DATA_MODE,
            kind="proposal",
            body={
                "proposal_id": proposal.proposal_id,
                "state": proposal.approval_state,
                "version": proposal.version,
                "kind": proposal.kind,
                "target": proposal.target,
                "author_id": owner.account_id,
            },
        )
