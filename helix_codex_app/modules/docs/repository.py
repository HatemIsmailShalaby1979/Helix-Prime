"""The storage layer for documents, their blocks, and their versions.

A document is one row in documents plus an ordered list of rows in
doc_blocks. Every query is scoped by tenant, and list_blocks is reached
only through a document the caller already owns, so a block never leaks
across documents or tenants. A snapshot writes the whole block list into
document_versions as one JSON row; a restore re-reads that snapshot and
appends a NEW version row, so history is never rewritten.
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

DOC_TYPE_NOTE = "note"
DOC_TYPE_SOP = "sop"
DOC_TYPE_KB = "kb"
DOC_TYPE_POLICY = "policy"
DOC_TYPES = (DOC_TYPE_NOTE, DOC_TYPE_SOP, DOC_TYPE_KB, DOC_TYPE_POLICY)
PUBLISHED_TYPES = (DOC_TYPE_SOP, DOC_TYPE_KB, DOC_TYPE_POLICY)
MANAGER_ROLES = ("owner", "manager")


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


@dataclass(frozen=True)
class Version:
    """One snapshot of a document's block list."""

    version_id: str
    document_id: str
    version_no: int
    snapshot: str
    created_by: str
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "version_id": self.version_id,
            "document_id": self.document_id,
            "version_no": self.version_no,
            "snapshot": self.snapshot,
            "created_by": self.created_by,
            "created_at": self.created_at,
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
        doc_types: tuple[str, ...] | None = None,
        visible_note_owner: str | None = None,
        include_all_notes: bool = False,
    ) -> list[Document]:
        """The documents of the tenant the caller can see, newest first.

        An optional search term filters titles, an optional status filters by
        the status column ('active' by default downstream), and an optional
        doc_types tuple narrows to those types (used by the KB view). When no
        type filter is given, a non-manager sees published types plus only the
        notes they own; include_all_notes widens to every document for a
        manager.
        """
        sql = """
            SELECT document_id, tenant_id, domain_id, title, doc_type,
                   owner_account_id, classification, status, current_version,
                   created_at, updated_at
            FROM documents
            WHERE tenant_id = ?
        """
        params: list[Any] = [tenant_id]
        if doc_types:
            placeholders = ", ".join("?" for _ in doc_types)
            sql += f" AND doc_type IN ({placeholders})"
            params.extend(doc_types)
        elif not include_all_notes:
            sql += " AND (doc_type IN ('sop', 'kb', 'policy') OR owner_account_id = ?)"
            params.append(visible_note_owner or "")
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

    def set_doc_type(self, document_id: str, tenant_id: str, doc_type: str) -> Document:
        """Change a document's type and return the updated row."""
        updated_at = _now()
        cursor = self.conn.execute(
            """
            UPDATE documents
            SET doc_type = ?, updated_at = ?
            WHERE document_id = ? AND tenant_id = ?
            """,
            (doc_type, updated_at, document_id, tenant_id),
        )
        if cursor.rowcount == 0:
            raise NotFoundError(f"no document {document_id!r} for this account")
        self.conn.commit()
        return self.get_document(document_id, tenant_id)

    def get_version(self, version_id: str, tenant_id: str) -> Version:
        """Load one version of a document owned by the tenant.

        document_versions has no tenant column, so the load joins the
        document row. A missing version or a version whose document belongs
        to another tenant raise the one NotFoundError shape.
        """
        row = self.conn.execute(
            """
            SELECT v.version_id, v.document_id, v.version_no, v.snapshot,
                   v.created_by, v.created_at
            FROM document_versions v
            JOIN documents d ON d.document_id = v.document_id
            WHERE v.version_id = ? AND d.tenant_id = ?
            """,
            (version_id, tenant_id),
        ).fetchone()
        if row is None:
            raise NotFoundError(f"no version {version_id!r} for this account")
        return _version_from_row(row)

    def get_version_by_no(self, document_id: str, version_no: int) -> Version:
        """Load the numbered version of one document, or NotFoundError."""
        row = self.conn.execute(
            """
            SELECT version_id, document_id, version_no, snapshot,
                   created_by, created_at
            FROM document_versions
            WHERE document_id = ? AND version_no = ?
            """,
            (document_id, version_no),
        ).fetchone()
        if row is None:
            raise NotFoundError(f"no version {version_no} of document {document_id!r}")
        return _version_from_row(row)

    def list_versions(self, document_id: str) -> list[Version]:
        """Every version of one document, newest first."""
        rows = self.conn.execute(
            """
            SELECT version_id, document_id, version_no, snapshot,
                   created_by, created_at
            FROM document_versions
            WHERE document_id = ?
            ORDER BY version_no DESC
            """,
            (document_id,),
        ).fetchall()
        return [_version_from_row(row) for row in rows]

    def create_version(
        self,
        *,
        document_id: str,
        version_no: int,
        snapshot: str,
        created_by: str,
    ) -> Version:
        """Append one version row and bump the document's current_version.

        The live blocks stay untouched; this method only writes history.
        The caller decides the version_no (the next one for the document's
        current state), which is why documents.current_version moves to
        version_no + 1 in the same commit.
        """
        version_id = _new_id("ver")
        created_at = _now()
        self.conn.execute(
            """
            INSERT INTO document_versions (
                version_id, document_id, version_no, snapshot,
                created_by, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (version_id, document_id, version_no, snapshot, created_by, created_at),
        )
        self.conn.execute(
            "UPDATE documents SET current_version = ?, updated_at = ? WHERE document_id = ?",
            (version_no + 1, created_at, document_id),
        )
        self.conn.commit()
        return Version(
            version_id=version_id,
            document_id=document_id,
            version_no=version_no,
            snapshot=snapshot,
            created_by=created_by,
            created_at=created_at,
        )

    def replace_blocks(
        self,
        document_id: str,
        blocks: list[dict[str, Any]],
        updated_by: str,
    ) -> list[Block]:
        """Replace the live block list with a snapshot's blocks.

        The snapshot's own block ids and ordinals are re-inserted, so a
        restore is a plain overwrite of the live list, never a touch on the
        version rows.
        """
        updated_at = _now()
        self.conn.execute("DELETE FROM doc_blocks WHERE document_id = ?", (document_id,))
        for block in blocks:
            self.conn.execute(
                """
                INSERT INTO doc_blocks (
                    block_id, document_id, ordinal, block_type, content,
                    updated_by, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    block["block_id"],
                    document_id,
                    block["ordinal"],
                    block["block_type"],
                    block["content"],
                    updated_by,
                    updated_at,
                ),
            )
        self.conn.commit()
        return self.list_blocks(document_id)

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


def _version_from_row(row: sqlite3.Row) -> Version:
    return Version(
        version_id=row["version_id"],
        document_id=row["document_id"],
        version_no=row["version_no"],
        snapshot=row["snapshot"],
        created_by=row["created_by"],
        created_at=row["created_at"],
    )
