"""The proposals projection: fast listing over the hash-chained ledger.

The JSONL ledger is the source of truth. These two tables exist so the UI can
list and filter proposals without replaying a ledger on every request. A
projection write never precedes the ledger write, so when the two disagree the
ledger wins and the projection is rebuilt from it.
"""
from __future__ import annotations

import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class ProposalRow:
    """One row of the proposals projection."""

    proposal_id: str
    store_id: str
    tenant_id: str
    domain_id: str | None
    kind: str
    target: str
    state: str
    version: int
    created_by: str
    role_id: str | None
    correlation_id: str | None
    classification: str | None
    data_mode: str | None
    created_at: str | None
    updated_at: str | None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_proposal(row: sqlite3.Row) -> ProposalRow:
    return ProposalRow(
        proposal_id=row["proposal_id"],
        store_id=row["store_id"],
        tenant_id=row["tenant_id"],
        domain_id=row["domain_id"],
        kind=row["kind"],
        target=row["target"],
        state=row["state"],
        version=int(row["version"] or 0),
        created_by=row["created_by"],
        role_id=row["role_id"],
        correlation_id=row["correlation_id"],
        classification=row["classification"],
        data_mode=row["data_mode"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


class MemoryRepository:
    """Reads and writes for the proposals and proposal_reviews projections."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def upsert_proposal(
        self,
        proposal: Any,
        *,
        store_id: str,
        domain_id: str | None,
    ) -> None:
        """Insert the proposal row, or refresh its state and version.

        Called only after the ledger has the record, never before.
        """
        now = _now()
        self.conn.execute(
            """
            INSERT INTO proposals (
                proposal_id, store_id, tenant_id, domain_id, kind, target, state, version,
                created_by, role_id, correlation_id, classification, data_mode,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(proposal_id) DO UPDATE SET
                state = excluded.state,
                version = excluded.version,
                updated_at = excluded.updated_at
            """,
            (
                proposal.proposal_id,
                store_id,
                proposal.tenant_id,
                domain_id,
                proposal.kind,
                proposal.target,
                proposal.approval_state,
                int(proposal.version),
                proposal.created_by,
                proposal.role_id,
                proposal.correlation_id,
                proposal.classification,
                proposal.data_mode,
                proposal.timestamp or now,
                now,
            ),
        )
        self.conn.commit()

    def get_proposal(self, proposal_id: str) -> ProposalRow | None:
        row = self.conn.execute(
            "SELECT * FROM proposals WHERE proposal_id = ?", (proposal_id,)
        ).fetchone()
        return _row_to_proposal(row) if row else None

    def list_proposals(
        self,
        tenant_id: str,
        *,
        state: str | None = None,
        created_by: str | None = None,
    ) -> list[ProposalRow]:
        """Proposals for one tenant, newest first, optionally filtered."""
        if not tenant_id or not tenant_id.strip():
            raise ValueError("list_proposals: tenant_id is required")
        sql = "SELECT * FROM proposals WHERE tenant_id = ?"
        params: list[Any] = [tenant_id]
        if state is not None:
            sql += " AND state = ?"
            params.append(state)
        if created_by is not None:
            sql += " AND created_by = ?"
            params.append(created_by)
        sql += " ORDER BY created_at DESC, proposal_id DESC"
        return [_row_to_proposal(row) for row in self.conn.execute(sql, params).fetchall()]

    def insert_review(
        self,
        *,
        proposal_id: str,
        reviewer_account_id: str,
        reviewer_role: str,
        decision: str,
        reason: str,
    ) -> str:
        """Record one review decision against a proposal."""
        review_id = f"review-{uuid.uuid4().hex}"
        self.conn.execute(
            """
            INSERT INTO proposal_reviews (
                review_id, proposal_id, reviewer_account_id, reviewer_role,
                decision, reason, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                review_id,
                proposal_id,
                reviewer_account_id,
                reviewer_role,
                decision,
                reason,
                _now(),
            ),
        )
        self.conn.commit()
        return review_id

    def list_reviews(self, proposal_id: str) -> list[sqlite3.Row]:
        return list(
            self.conn.execute(
                "SELECT * FROM proposal_reviews WHERE proposal_id = ? ORDER BY created_at",
                (proposal_id,),
            ).fetchall()
        )
