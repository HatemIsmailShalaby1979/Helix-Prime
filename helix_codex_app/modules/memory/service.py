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
from helix_codex_app.modules.memory.repository import MemoryRepository, PromotionRow, ProposalRow
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
PROMOTION_APPROVER_ROLES = ("manager", "owner")
PROMOTED_RULE_SOURCE = "memory_promotion"


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

    # ------------------------------------------------------------- reviewing
    def review_queue(self, account: Account) -> list[dict[str, Any]]:
        """Proposals in this tenant waiting for this account's review.

        Excludes the account's own proposals and any author sharing the account's
        role, because the engine would refuse those anyway. Showing a button that
        can only fail is worse than not showing it.
        """
        out: list[dict[str, Any]] = []
        for row in self.repo.list_proposals(account.tenant_id, state="evaluated"):
            if row.created_by == account.account_id:
                continue
            author = self.accounts.get_account_by_id(row.created_by)
            if author is None or (author.role_id or "") == (account.role_id or ""):
                continue
            out.append({"row": row, "author": author})
        return out

    def review_report(self, account: Account, proposal_id: str) -> dict:
        """The evidence report for a proposal this account may review.

        Separate from evidence_report() on purpose: that one is the author's own
        view, this one is the reviewer's, and it re-checks that the reviewer is
        allowed before handing anything over.
        """
        owner = self._owner_of(account, proposal_id)
        if owner.account_id == account.account_id:
            raise NotFoundError(
                f"no such proposal {proposal_id}", payload={"proposal_id": proposal_id}
            )
        if (owner.role_id or "") == (account.role_id or ""):
            raise PermissionDenied(
                "same-role review is not allowed",
                payload={"proposal_id": proposal_id},
            )
        return self.engines.evidence_report(owner, self.engines.get(owner, proposal_id))

    def card_view(self, account: Account, proposal_id: str) -> dict[str, Any] | None:
        """The proposal as this account is allowed to see it, or None.

        The author's own view first, then the reviewer's. None means the account
        may not see this proposal at all, and the caller should show nothing.
        """
        try:
            return {
                "proposal": self.evidence_report(account, proposal_id),
                "author_name": None,
                "is_own": True,
            }
        except NotFoundError:
            pass
        try:
            owner = self._owner_of(account, proposal_id)
            return {
                "proposal": self.review_report(account, proposal_id),
                "author_name": owner.display_name or owner.username,
                "is_own": False,
            }
        except (NotFoundError, PermissionDenied):
            return None

    # ------------------------------------------------------------ promotion
    def request_promotion(self, account: Account, proposal_id: str) -> PromotionRow:
        """Ask for an approved proposal to become a company-wide rule.

        The author's own approval is never enough. This only creates the
        org-level proposal; a manager or owner has to approve that one
        separately, and the two approvals are recorded as two decisions.
        """
        source = self.get_proposal(account, proposal_id)
        if source.approval_state != "approved":
            raise InvalidStateError(
                f"{proposal_id}: only an approved proposal can be promoted "
                f"(state is {source.approval_state!r})",
                payload={"proposal_id": proposal_id},
            )
        promotion_id = f"promo-{uuid.uuid4().hex}"
        org_proposal = self.engines.org_propose(
            account,
            kind=source.kind,
            target=f"promoted::{source.proposal_id}",
            baseline=source.baseline,
            proposed=source.proposed,
            baseline_policy=dict(source.baseline_policy),
            proposed_policy=dict(source.proposed_policy),
            hypothesis=source.hypothesis,
            evidence=[source.proposal_id, *source.evidence],
            risk_assessment=source.risk_assessment,
            rollback_plan=f"roll back promotion {promotion_id}",
            tenant_id=account.tenant_id,
            client_id=account.client_id or "",
            created_by=account.account_id,
            role_id=account.role_id or "",
            correlation_id=source.correlation_id,
            timestamp=_now(),
            min_improvement=source.min_improvement,
        )
        org_cases = cases_from_memory(self.stores.read_org(account, limit=MAX_EVIDENCE_CASES))
        self.engines.org_evaluate(
            account,
            org_proposal,
            historical_cases=org_cases,
            simulated_cases=[],
            simulate=default_simulate,
        )
        self.repo.insert_promotion(
            promotion_id=promotion_id,
            source_store_id=db.store_id_for(path=self.engines.resolve_path(account)),
            org_store_id=db.store_id_for(path=self.engines.resolve_org_path(account)),
            source_proposal_id=source.proposal_id,
            org_proposal_id=org_proposal.proposal_id,
        )
        row = self.repo.get_promotion(promotion_id)
        if row is None:
            raise NotFoundError(f"promotion {promotion_id} vanished after insert")
        return row

    def approve_promotion(
        self, account: Account, promotion_id: str, *, reason: str = ""
    ) -> PromotionRow:
        """Approve a promotion. Needs a manager or owner, and a second person."""
        promotion = self._promotion_for(account, promotion_id)
        if promotion.state != "requested":
            raise InvalidStateError(
                f"{promotion_id}: not awaiting approval (state is {promotion.state!r})",
                payload={"promotion_id": promotion_id},
            )
        author = self._owner_of(account, promotion.source_proposal_id)
        if author.account_id == account.account_id:
            raise PermissionDenied(
                "a promotion needs a second, independent approver",
                payload={"promotion_id": promotion_id},
            )
        if (account.role_id or "") not in PROMOTION_APPROVER_ROLES:
            raise PermissionDenied(
                "only a manager or owner may approve a promotion",
                payload={"promotion_id": promotion_id},
            )
        try:
            decision = self.engines.org_approve(
                account,
                promotion.org_proposal_id,
                reviewer=account.account_id,
                approver_role=account.role_id or "",
            )
        except ProposalNotApprovableError as exc:
            raise InvalidStateError(str(exc), payload={"promotion_id": promotion_id}) from exc
        if decision.decision != "allowed":
            raise PermissionDenied(decision.reason, payload={"promotion_id": promotion_id})
        self.stores.record_org(
            account,
            kind="policy",
            nature="user_claim",
            body={
                "promotion_id": promotion_id,
                "rule": promotion.source_proposal_id,
                "promoted_from_account_id": author.account_id,
                "source_proposal_id": promotion.source_proposal_id,
            },
            evidence_refs=[promotion.source_proposal_id],
            source="memory_promotion",
            correlation_id=f"promotion-{promotion_id}",
        )
        self.repo.update_promotion(promotion_id, state="approved", approved_by=account.account_id)
        return self._promotion_for(account, promotion_id)

    def reject_promotion(self, account: Account, promotion_id: str, *, reason: str) -> PromotionRow:
        """Refuse a promotion. Needs a reason, and the same second-person rule."""
        if not reason or not reason.strip():
            raise ValueError("a rejection needs a reason")
        promotion = self._promotion_for(account, promotion_id)
        if promotion.state != "requested":
            raise InvalidStateError(
                f"{promotion_id}: not awaiting a decision (state is {promotion.state!r})",
                payload={"promotion_id": promotion_id},
            )
        author = self._owner_of(account, promotion.source_proposal_id)
        if author.account_id == account.account_id:
            raise PermissionDenied(
                "a promotion needs a second, independent decider",
                payload={"promotion_id": promotion_id},
            )
        if (account.role_id or "") not in PROMOTION_APPROVER_ROLES:
            raise PermissionDenied(
                "only a manager or owner may decide a promotion",
                payload={"promotion_id": promotion_id},
            )
        self.engines.org_engine_for(account).reject(
            promotion.org_proposal_id, reviewer=account.account_id, reason=reason
        )
        self.repo.update_promotion(promotion_id, state="rejected", approved_by=account.account_id)
        return self._promotion_for(account, promotion_id)

    def rollback_promotion(
        self, account: Account, promotion_id: str, *, reason: str = ""
    ) -> PromotionRow:
        """Undo a promotion: retire the org rule and record the reversal twice."""
        promotion = self._promotion_for(account, promotion_id)
        if promotion.state != "approved":
            raise InvalidStateError(
                f"{promotion_id}: not an approved promotion (state is {promotion.state!r})",
                payload={"promotion_id": promotion_id},
            )
        author = self._owner_of(account, promotion.source_proposal_id)
        note = reason or "promotion rolled back"
        self.engines.org_rollback(
            account, promotion.org_proposal_id, actor=account.account_id, reason=note
        )
        rule = self._promoted_rule(account, promotion_id)
        if rule is not None:
            self.stores.org_store_for(account).delete(
                record_id=rule.record_id,
                actor=account.account_id,
                role_id=account.role_id or "",
                reason=note,
                timestamp=_now(),
            )
        self.stores.record(
            author,
            kind="workflow_history",
            nature="verified_outcome",
            body={"note": "promotion rolled back", "promotion_id": promotion_id},
            source="promotion_reversal",
            correlation_id=f"promotion-{promotion_id}",
        )
        self.repo.update_promotion(promotion_id, state="rolled_back")
        return self._promotion_for(account, promotion_id)

    def list_promotions(self, account: Account, *, state: str | None = None) -> list[PromotionRow]:
        """Promotions raised inside this account's tenant."""
        return self.repo.list_promotions_for_tenant(account.tenant_id, state=state)

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

    def _promotion_for(self, account: Account, promotion_id: str) -> PromotionRow:
        """One promotion, scoped to the caller's tenant."""
        row = self.repo.get_promotion(promotion_id)
        if row is None:
            raise NotFoundError(
                f"no such promotion {promotion_id}", payload={"promotion_id": promotion_id}
            )
        author = self._owner_of(account, row.source_proposal_id)
        if author.tenant_id != account.tenant_id:
            raise NotFoundError(
                f"no such promotion {promotion_id}", payload={"promotion_id": promotion_id}
            )
        return row

    def _promoted_rule(self, account: Account, promotion_id: str) -> Any | None:
        """The single org record a promotion created, or None.

        Found by the promotion id carried in the record body. If more than one
        record claims the same promotion, that is ambiguous, so it is refused
        rather than guessed at. A dedicated column would be tidier and is noted
        as a known limitation.
        """
        matches = [
            record
            for record in self.stores.read_org(account, limit=MAX_EVIDENCE_CASES)
            if record.body.get("promotion_id") == promotion_id
        ]
        if len(matches) > 1:
            raise InvalidStateError(
                f"{promotion_id}: more than one org rule claims this promotion",
                payload={"promotion_id": promotion_id, "matches": len(matches)},
            )
        return matches[0] if matches else None

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
