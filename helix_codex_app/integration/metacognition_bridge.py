"""Per-store metacognition engines for the app.

Every account gets its own proposals ledger, and each domain gets one org
proposals ledger, mirroring the memory stores. One engine instance per ledger,
resolved from the authenticated account exactly the way a memory store is, so a
caller cannot name a foreign ledger.

This module is the only place in the app that imports the parent metacognition
package. Feature modules use the engine through AccountMetacognition and the
re-exported proposal types below, never by importing the parent directly.
"""
from __future__ import annotations

import pathlib
from typing import Any, Callable, Mapping, Sequence

from helix_codex_app.config import get_app_settings
from helix_codex_app.integration.memory_bridge import ORG_KEY, safe_component
from helix_codex_app.security.accounts import Account
from metacognition.improvement import (
    ApprovalDecision,
    EvaluationResult,
    ImprovementProposal,
    MetacognitionEngine,
    ProposalNotApprovableError,
    ProposalStateError,
)

__all__ = [
    "AccountMetacognition",
    "ApprovalDecision",
    "EvaluationResult",
    "ImprovementProposal",
    "ProposalNotApprovableError",
    "ProposalStateError",
    "resolve_proposals_path",
]

PROPOSALS_FILENAME = "proposals.jsonl"


def resolve_proposals_path(*, memory_root: str, domain_id: str, account_id: str | None) -> str:
    """Compute a proposals-ledger path from server-side values.

    account_id None means the domain's shared org ledger. Validated the same way
    a memory store path is, so a value that arrived from a form cannot escape.
    """
    domain = safe_component(domain_id, field="domain_id")
    key = safe_component(account_id, field="account_id") if account_id else ORG_KEY
    return str(pathlib.Path(memory_root) / domain / key / PROPOSALS_FILENAME)


class AccountMetacognition:
    """Metacognition engines bound to one account, plus the domain's org engine."""

    def __init__(self, *, memory_root: str | None = None) -> None:
        self._root = memory_root or get_app_settings().memory_root
        self._engines: dict[str, MetacognitionEngine] = {}

    # ------------------------------------------------------------ resolution
    def resolve_path(self, account: Account) -> str:
        """The account's own proposals ledger. Never derived from a request."""
        if not account.domain_id or not account.account_id:
            raise ValueError("metacognition: domain_id and account_id are required")
        return resolve_proposals_path(
            memory_root=self._root,
            domain_id=account.domain_id,
            account_id=account.account_id,
        )

    def resolve_org_path(self, account: Account) -> str:
        """The domain's shared org proposals ledger."""
        if not account.domain_id:
            raise ValueError("metacognition: domain_id is required")
        return resolve_proposals_path(
            memory_root=self._root,
            domain_id=account.domain_id,
            account_id=None,
        )

    def engine_for(self, account: Account) -> MetacognitionEngine:
        return self._open(self.resolve_path(account))

    def org_engine_for(self, account: Account) -> MetacognitionEngine:
        return self._open(self.resolve_org_path(account))

    def _open(self, path: str) -> MetacognitionEngine:
        engine = self._engines.get(path)
        if engine is None:
            pathlib.Path(path).parent.mkdir(parents=True, exist_ok=True)
            engine = MetacognitionEngine(path=path)
            self._engines[path] = engine
        return engine

    # -------------------------------------------------------------- account
    def propose(self, account: Account, **kwargs: Any) -> ImprovementProposal:
        return self.engine_for(account).propose(**kwargs)

    def get(self, account: Account, proposal_id: str) -> ImprovementProposal:
        return self.engine_for(account).get_proposal(proposal_id)

    def list(self, account: Account, *, state: str | None = None) -> list[ImprovementProposal]:
        return self.engine_for(account).list_proposals(tenant_id=account.tenant_id, state=state)

    def evaluate(
        self,
        account: Account,
        proposal: ImprovementProposal,
        *,
        historical_cases: Sequence[Mapping[str, Any]],
        simulated_cases: Sequence[Mapping[str, Any]],
        simulate: Callable[[Mapping[str, Any], Mapping[str, Any]], bool],
    ) -> EvaluationResult:
        return self.engine_for(account).evaluate(
            proposal, historical_cases, simulated_cases, simulate
        )

    def approve(
        self, account: Account, proposal_id: str, *, reviewer: str, approver_role: str
    ) -> ApprovalDecision:
        return self.engine_for(account).approve(proposal_id, reviewer, approver_role)

    def reject(
        self, account: Account, proposal_id: str, *, reviewer: str, reason: str
    ) -> ImprovementProposal:
        return self.engine_for(account).reject(proposal_id, reviewer, reason)

    def rollback(
        self, account: Account, proposal_id: str, *, actor: str, reason: str
    ) -> ImprovementProposal:
        return self.engine_for(account).rollback(proposal_id, actor, reason)

    def evidence_report(self, account: Account, proposal: ImprovementProposal) -> dict:
        return self.engine_for(account).generate_evidence_report(proposal)

    def verify_chain(self, account: Account) -> tuple[bool, str]:
        return self.engine_for(account).verify_chain()

    # ------------------------------------------------------------------ org
    def org_propose(self, account: Account, **kwargs: Any) -> ImprovementProposal:
        return self.org_engine_for(account).propose(**kwargs)

    def org_get(self, account: Account, proposal_id: str) -> ImprovementProposal:
        return self.org_engine_for(account).get_proposal(proposal_id)

    def org_evaluate(
        self,
        account: Account,
        proposal: ImprovementProposal,
        *,
        historical_cases: Sequence[Mapping[str, Any]],
        simulated_cases: Sequence[Mapping[str, Any]],
        simulate: Callable[[Mapping[str, Any], Mapping[str, Any]], bool],
    ) -> EvaluationResult:
        return self.org_engine_for(account).evaluate(
            proposal, historical_cases, simulated_cases, simulate
        )

    def org_list(self, account: Account, *, state: str | None = None) -> list[ImprovementProposal]:
        return self.org_engine_for(account).list_proposals(tenant_id=account.tenant_id, state=state)

    def org_approve(
        self, account: Account, proposal_id: str, *, reviewer: str, approver_role: str
    ) -> ApprovalDecision:
        return self.org_engine_for(account).approve(proposal_id, reviewer, approver_role)

    def org_rollback(
        self, account: Account, proposal_id: str, *, actor: str, reason: str
    ) -> ImprovementProposal:
        return self.org_engine_for(account).rollback(proposal_id, actor, reason)

    def org_verify_chain(self, account: Account) -> tuple[bool, str]:
        return self.org_engine_for(account).verify_chain()
