"""The storage layer for documents and their blocks.

A document is one row in documents plus an ordered list of rows in
doc_blocks. Every query is scoped by tenant, and list_blocks is reached
only through a document the caller already owns, so a block never leaks
across documents or tenants.
"""
from __future__ import annotations

import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from helix_codex_app.errors import NotFoundError

MAX_TITLE_LENGTH = 200
MAX_BLOCK_LENGTH = 20000


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex}"


@dataclass(frozen=True)
class Document:
    """One document row."""

    document_id: str
    tenant_id: str
    domain_id: str | None
    title: str
    doc_type: str
    owner_account_id: str
    classification: str
    status: str
    current_version: int
    created_at: str
    updated_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "document_id": self.document_id,
            "tenant_id": self.tenant_id,
            "domain_id": self.domain_id,
            "title": self.title,
            "doc_type": self.doc_type,
            "owner_account_id": self.owner_account_id,
            "classification": self.classification,
            "status": self.status,
            "current_version": self.current_version,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass(frozen=True)
class Block:
    """One block row inside a document."""

    block_id: str
    document_id: str
    ordinal: int
    block_type: str
    content: str
    updated_by: str
    updated_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "block_id": self.block_id,
            "document_id": self.document_id,
            "ordinal": self.ordinal,
            "block_type": self.block_type,
            "content": self.content,
            "updated_by": self.updated_by,
            "updated_at": self.updated_at,
        }


class DocsRepository:
    """The read and write surface for the documents tables."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def create_document(
        self,
        *,
        tenant_id: str,
        domain_id: str | None,
        title: str,
        doc_type: str,
        owner_account_id: str,
        classification: str,
    ) -> Document:
        """Insert one document row and return it. Blocks are added later."""
        document_id = _new_id("doc")
        created_at = _now()
        self.conn.execute(
            """
            INSERT INTO documents (
                document_id, tenant_id, domain_id, title, doc_type,
                owner_account_id, classification, status, current_version,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'active', 1, ?, ?)
            """,
            (
                document_id,
                tenant_id,
                domain_id,
                title,
                doc_type,
                owner_account_id,
                classification,
                created_at,
                created_at,
            ),
        )
        self.conn.commit()
        return self.get_document(document_id, tenant_id)

    def get_document(self, document_id: str, tenant_id: str) -> Document:
        """Load one document owned by the tenant.

        Raises NotFoundError when the document is missing OR belongs to
        another tenant, with one message shape for either case.
        """
        row = self.conn.execute(
            """
            SELECT document_id, tenant_id, domain_id, title, doc_type,
                   owner_account_id, classification, status, current_version,
                   created_at, updated_at
            FROM documents
            WHERE document_id = ? AND tenant_id = ?
            """,
            (document_id, tenant_id),
        ).fetchone()
        if row is None:
            raise NotFoundError(f"no document {document_id!r} for this account")
        return _document_from_row(row)

    def list_documents(
        self,
        tenant_id: str,
        *,
        q: str | None = None,
        status: str | None = None,
    ) -> list[Document]:
        """Every document of the tenant, newest update first.

        An optional search term filters titles, and an optional status
        filters by the status column ('active' by default downstream).
        """
        sql = """
            SELECT document_id, tenant_id, domain_id, title, doc_type,
                   owner_account_id, classification, status, current_version,
                   created_at, updated_at
            FROM documents
            WHERE tenant_id = ?
        """
        params: list[Any] = [tenant_id]
        if q:
            sql += " AND title LIKE ?"
            params.append(f"%{q}%")
        if status:
            sql += " AND status = ?"
            params.append(status)
        sql += " ORDER BY updated_at DESC, document_id DESC"
        rows = self.conn.execute(sql, params).fetchall()
        return [_document_from_row(row) for row in rows]

    def set_status(self, document_id: str, tenant_id: str, status: str) -> Document:
        """Change a document's status and return the updated row."""
        updated_at = _now()
        cursor = self.conn.execute(
            """
            UPDATE documents
            SET status = ?, updated_at = ?
            WHERE document_id = ? AND tenant_id = ?
            """,
            (status, updated_at, document_id, tenant_id),
        )
        if cursor.rowcount == 0:
            raise NotFoundError(f"no document {document_id!r} for this account")
        self.conn.commit()
        return self.get_document(document_id, tenant_id)

    def list_blocks(self, document_id: str) -> list[Block]:
        """The blocks of one document, in order."""
        rows = self.conn.execute(
            """
            SELECT block_id, document_id, ordinal, block_type, content,
                   updated_by, updated_at
            FROM doc_blocks
            WHERE document_id = ?
            ORDER BY ordinal, block_id
            """,
            (document_id,),
        ).fetchall()
        return [_block_from_row(row) for row in rows]

    def get_block(self, document_id: str, block_id: str) -> Block:
        """Load one block that belongs to the given document.

        Raises NotFoundError when the block is missing or when the block
        belongs to a different document, so a caller cannot reach another
        document's block through the wrong id.
        """
        row = self.conn.execute(
            """
            SELECT block_id, document_id, ordinal, block_type, content,
                   updated_by, updated_at
            FROM doc_blocks
            WHERE block_id = ? AND document_id = ?
            """,
            (block_id, document_id),
        ).fetchone()
        if row is None:
            raise NotFoundError(f"no block {block_id!r} in document {document_id!r}")
        return _block_from_row(row)

    def append_block(
        self,
        *,
        document_id: str,
        block_type: str,
        content: str,
        updated_by: str,
    ) -> Block:
        """Add one block at the end of a document."""
        blocks = self.list_blocks(document_id)
        ordinal = blocks[-1].ordinal + 1 if blocks else 0
        return self.insert_block(
            document_id=document_id,
            ordinal=ordinal,
            block_type=block_type,
            content=content,
            updated_by=updated_by,
        )

    def insert_block(
        self,
        *,
        document_id: str,
        ordinal: int,
        block_type: str,
        content: str,
        updated_by: str,
    ) -> Block:
        """Insert one block at the given position, shifting later blocks up."""
        block_id = _new_id("blk")
        updated_at = _now()
        self.conn.execute(
            """
            UPDATE doc_blocks
            SET ordinal = ordinal + 1
            WHERE document_id = ? AND ordinal >= ?
            """,
            (document_id, ordinal),
        )
        self.conn.execute(
            """
            INSERT INTO doc_blocks (
                block_id, document_id, ordinal, block_type, content,
                updated_by, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                block_id,
                document_id,
                ordinal,
                block_type,
                content,
                updated_by,
                updated_at,
            ),
        )
        self.conn.commit()
        return self.get_block(document_id, block_id)

    def update_block(
        self,
        *,
        document_id: str,
        block_id: str,
        content: str,
        updated_by: str,
    ) -> Block:
        """Set a block's content, only when it belongs to the document."""
        updated_at = _now()
        cursor = self.conn.execute(
            """
            UPDATE doc_blocks
            SET content = ?, updated_by = ?, updated_at = ?
            WHERE block_id = ? AND document_id = ?
            """,
            (content, updated_by, updated_at, block_id, document_id),
        )
        if cursor.rowcount == 0:
            raise NotFoundError(f"no block {block_id!r} in document {document_id!r}")
        self.conn.commit()
        return self.get_block(document_id, block_id)

    def delete_block(self, document_id: str, block_id: str) -> bool:
        """Remove one block and close the gap in the ordinals.

        Returns False when the row was already gone or belongs to another
        document.
        """
        cursor = self.conn.execute(
            "DELETE FROM doc_blocks WHERE block_id = ? AND document_id = ?",
            (block_id, document_id),
        )
        if cursor.rowcount == 0:
            return False
        self._renumber(document_id)
        self.conn.commit()
        return True

    def reorder_blocks(self, document_id: str, ordered_block_ids: list[str]) -> list[Block]:
        """Rewrite ordinal so the given id order is the document's order.

        Raises ValueError when the list does not contain exactly the
        document's blocks.
        """
        existing = self.list_blocks(document_id)
        existing_ids = {block.block_id for block in existing}
        if set(ordered_block_ids) != existing_ids or len(ordered_block_ids) != len(existing_ids):
            raise ValueError("reorder must name every block of the document exactly once")
        for ordinal, block_id in enumerate(ordered_block_ids):
            self.conn.execute(
                "UPDATE doc_blocks SET ordinal = ? WHERE block_id = ? AND document_id = ?",
                (ordinal, block_id, document_id),
            )
        self.conn.commit()
        return self.list_blocks(document_id)

    def _renumber(self, document_id: str) -> None:
        """Make ordinals contiguous after a deletion."""
        blocks = self.list_blocks(document_id)
        for ordinal, block in enumerate(blocks):
            self.conn.execute(
                "UPDATE doc_blocks SET ordinal = ? WHERE block_id = ?",
                (ordinal, block.block_id),
            )


def _document_from_row(row: sqlite3.Row) -> Document:
    return Document(
        document_id=row["document_id"],
        tenant_id=row["tenant_id"],
        domain_id=row["domain_id"],
        title=row["title"],
        doc_type=row["doc_type"],
        owner_account_id=row["owner_account_id"],
        classification=row["classification"],
        status=row["status"],
        current_version=row["current_version"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _block_from_row(row: sqlite3.Row) -> Block:
    return Block(
        block_id=row["block_id"],
        document_id=row["document_id"],
        ordinal=row["ordinal"],
        block_type=row["block_type"],
        content=row["content"],
        updated_by=row["updated_by"],
        updated_at=row["updated_at"],
    )
