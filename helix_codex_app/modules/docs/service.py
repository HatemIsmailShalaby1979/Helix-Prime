"""The write and read surface for documents and their blocks.

The service owns the rules the repository cannot express on its own: a
document carries a title inside one tenant, blocks arrive in order, and
every human write lands as a governed node through record_node() with kind
document or block, so documents are in the audit trail like every other
write in the app. Tenant and client ids come from the actor's account
record; the request never supplies them. One writer per block: the later
write wins and both writes are recorded.
"""
from __future__ import annotations

import sqlite3
import uuid
from typing import Any

from helix_codex_app.db import record_node
from helix_codex_app.modules.docs.repository import (
    MAX_BLOCK_LENGTH,
    MAX_TITLE_LENGTH,
    Block,
    DocsRepository,
    Document,
)
from helix_codex_app.security.accounts import Account

PROVENANCE_SOURCE = "helix_codex_app.docs"
PROVENANCE_DATA_MODE = "app_runtime"
DOC_TYPE_NOTE = "note"
ARCHIVED = "archived"


class DocsService:
    """Documents and blocks, with the governance envelope attached."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self.repo = DocsRepository(conn)

    def create_document(
        self,
        account: Account,
        title: str,
        *,
        doc_type: str = DOC_TYPE_NOTE,
    ) -> Document:
        """Create a new document owned by the account's tenant."""
        if not title or not title.strip():
            raise ValueError("a document needs a title")
        title = title.strip()
        if len(title) > MAX_TITLE_LENGTH:
            raise ValueError(f"a document title holds at most {MAX_TITLE_LENGTH} characters")
        document = self.repo.create_document(
            tenant_id=account.tenant_id,
            domain_id=account.domain_id,
            title=title,
            doc_type=doc_type,
            owner_account_id=account.account_id,
            classification="internal",
        )
        record_node(
            self.conn,
            tenant_id=account.tenant_id,
            client_id=account.client_id,
            domain_id=account.domain_id,
            correlation_id=self._correlation_id(),
            classification="internal",
            nature="user_claim",
            created_by=account.account_id,
            provenance_source=PROVENANCE_SOURCE,
            provenance_data_mode=PROVENANCE_DATA_MODE,
            kind="document",
            body={
                "document_id": document.document_id,
                "title": document.title,
                "doc_type": document.doc_type,
            },
        )
        return document

    def get_document(self, account: Account, document_id: str) -> Document:
        """One document, tenant enforced."""
        return self.repo.get_document(document_id, account.tenant_id)

    def list_documents(
        self,
        account: Account,
        filters: dict[str, Any] | None = None,
    ) -> list[Document]:
        """Every active document of the tenant, newest update first."""
        filters = filters or {}
        return self.repo.list_documents(
            account.tenant_id,
            q=filters.get("q") or None,
            status=filters.get("status") or "active",
        )

    def list_blocks(self, account: Account, document_id: str) -> list[Block]:
        """The blocks of one document, in order."""
        self.repo.get_document(document_id, account.tenant_id)
        return self.repo.list_blocks(document_id)

    def get_block(self, account: Account, document_id: str, block_id: str) -> Block:
        """One block, scoped to its document and the caller's tenant."""
        self.repo.get_document(document_id, account.tenant_id)
        return self.repo.get_block(document_id, block_id)

    def insert_block(
        self,
        account: Account,
        document_id: str,
        content: str,
        *,
        block_type: str = "text",
    ) -> Block:
        """Append one block to a document and record the write."""
        _validate_content(content)
        document = self.repo.get_document(document_id, account.tenant_id)
        block = self.repo.append_block(
            document_id=document_id,
            block_type=block_type,
            content=content,
            updated_by=account.account_id,
        )
        record_node(
            self.conn,
            tenant_id=document.tenant_id,
            client_id=account.client_id,
            domain_id=document.domain_id,
            correlation_id=self._correlation_id(),
            classification="internal",
            nature="user_claim",
            created_by=account.account_id,
            provenance_source=PROVENANCE_SOURCE,
            provenance_data_mode=PROVENANCE_DATA_MODE,
            kind="block",
            body={
                "block_id": block.block_id,
                "document_id": block.document_id,
                "ordinal": block.ordinal,
                "block_type": block.block_type,
                "content": block.content,
            },
        )
        return block

    def update_block(
        self,
        account: Account,
        document_id: str,
        block_id: str,
        content: str,
    ) -> Block:
        """Overwrite one block. The later write wins and is recorded too."""
        _validate_content(content)
        document = self.repo.get_document(document_id, account.tenant_id)
        block = self.repo.update_block(
            document_id=document_id,
            block_id=block_id,
            content=content,
            updated_by=account.account_id,
        )
        record_node(
            self.conn,
            tenant_id=document.tenant_id,
            client_id=account.client_id,
            domain_id=document.domain_id,
            correlation_id=self._correlation_id(),
            classification="internal",
            nature="user_claim",
            created_by=account.account_id,
            provenance_source=PROVENANCE_SOURCE,
            provenance_data_mode=PROVENANCE_DATA_MODE,
            kind="block",
            body={
                "block_id": block.block_id,
                "document_id": block.document_id,
                "content": block.content,
            },
        )
        return block

    def delete_block(
        self,
        account: Account,
        document_id: str,
        block_id: str,
    ) -> bool:
        """Remove one block and record the write."""
        document = self.repo.get_document(document_id, account.tenant_id)
        removed = self.repo.delete_block(document_id, block_id)
        if removed:
            record_node(
                self.conn,
                tenant_id=document.tenant_id,
                client_id=account.client_id,
                domain_id=document.domain_id,
                correlation_id=self._correlation_id(),
                classification="internal",
                nature="user_claim",
                created_by=account.account_id,
                provenance_source=PROVENANCE_SOURCE,
                provenance_data_mode=PROVENANCE_DATA_MODE,
                kind="block",
                body={"block_id": block_id, "document_id": document_id, "deleted": True},
            )
        return removed

    def reorder_blocks(
        self,
        account: Account,
        document_id: str,
        ordered_block_ids: list[str],
    ) -> list[Block]:
        """Rewire the document's order and record the write."""
        document = self.repo.get_document(document_id, account.tenant_id)
        self.repo.reorder_blocks(document_id, ordered_block_ids)
        record_node(
            self.conn,
            tenant_id=document.tenant_id,
            client_id=account.client_id,
            domain_id=document.domain_id,
            correlation_id=self._correlation_id(),
            classification="internal",
            nature="user_claim",
            created_by=account.account_id,
            provenance_source=PROVENANCE_SOURCE,
            provenance_data_mode=PROVENANCE_DATA_MODE,
            kind="block",
            body={"document_id": document_id, "order": ordered_block_ids},
        )
        return self.repo.list_blocks(document_id)

    def archive_document(self, account: Account, document_id: str) -> Document:
        """Move a document out of the active list and record the write."""
        document = self.repo.set_status(document_id, account.tenant_id, ARCHIVED)
        record_node(
            self.conn,
            tenant_id=document.tenant_id,
            client_id=account.client_id,
            domain_id=document.domain_id,
            correlation_id=self._correlation_id(),
            classification="internal",
            nature="user_claim",
            created_by=account.account_id,
            provenance_source=PROVENANCE_SOURCE,
            provenance_data_mode=PROVENANCE_DATA_MODE,
            kind="document",
            body={"document_id": document.document_id, "status": ARCHIVED},
        )
        return document

    @staticmethod
    def _correlation_id() -> str:
        return f"doc-{uuid.uuid4().hex}"


def _validate_content(content: str) -> None:
    if content is None:
        raise ValueError("a block needs content")
    if len(content) > MAX_BLOCK_LENGTH:
        raise ValueError(f"a block holds at most {MAX_BLOCK_LENGTH} characters")
