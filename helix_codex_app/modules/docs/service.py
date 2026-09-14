"""The write and read surface for documents, their blocks, and versions.

The service owns the rules the repository cannot express on its own: a
document carries a title inside one tenant, blocks arrive in order, and
every human write lands as a governed node through record_node() with kind
document, block, or version, so documents are in the audit trail like every
other write in the app. Tenant and client ids come from the actor's account
record; the request never supplies them. One writer per block: the later
write wins and both writes are recorded.

A snapshot writes the whole block list into a version row without touching
the live blocks; a restore appends a NEW version whose content equals the
old one and then overwrites the live block list, so history is append-only.
A note is like a working paper: only its owner and managers may read it. A
published document (sop, kb, policy) is readable by everyone in the tenant.
Only a manager or owner may publish sop or policy.
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from typing import Any

from helix_codex_app.db import record_node
from helix_codex_app.errors import NotFoundError, PermissionDenied
from helix_codex_app.modules.docs.repository import (
    DOC_TYPE_NOTE,
    DOC_TYPE_POLICY,
    DOC_TYPE_SOP,
    DOC_TYPES,
    MANAGER_ROLES,
    MAX_BLOCK_LENGTH,
    MAX_TITLE_LENGTH,
    Block,
    DocsRepository,
    Document,
    Version,
)
from helix_codex_app.security.accounts import Account

PROVENANCE_SOURCE = "helix_codex_app.docs"
PROVENANCE_DATA_MODE = "app_runtime"
ARCHIVED = "archived"


class DocsService:
    """Documents, blocks, and versions, with the governance envelope attached."""

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
        if doc_type not in DOC_TYPES:
            raise ValueError(f"doc_type must be one of {', '.join(DOC_TYPES)}")
        if doc_type in (DOC_TYPE_SOP, DOC_TYPE_POLICY) and account.role_id not in MANAGER_ROLES:
            raise PermissionDenied("only a manager or owner may publish an sop or policy")
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
        """One document, tenant and note visibility enforced.

        A note owned by someone else is invisible to a non-manager, so a
        peer employee reads and edits it as if it did not exist.
        """
        document = self.repo.get_document(document_id, account.tenant_id)
        self._require_readable(account, document)
        return document

    def list_documents(
        self,
        account: Account,
        filters: dict[str, Any] | None = None,
    ) -> list[Document]:
        """The documents of the tenant the account can see, newest first.

        A non-manager sees published types plus only the notes they own; a
        manager sees every note. doc_types narrows to those types alone (the
        KB view), where every listed type is published by construction.
        """
        filters = filters or {}
        doc_types = filters.get("doc_types")
        return self.repo.list_documents(
            account.tenant_id,
            q=filters.get("q") or None,
            status=filters.get("status") or "active",
            doc_types=tuple(doc_types) if doc_types else None,
            visible_note_owner=account.account_id,
            include_all_notes=account.role_id in MANAGER_ROLES,
        )

    def set_doc_type(self, account: Account, document_id: str, doc_type: str) -> Document:
        """Change a document's type and record the write.

        Only a manager or owner may set sop or policy; kb is open to any
        writer, exactly as the pack spells out.
        """
        if doc_type not in DOC_TYPES:
            raise ValueError(f"doc_type must be one of {', '.join(DOC_TYPES)}")
        if doc_type in (DOC_TYPE_SOP, DOC_TYPE_POLICY) and account.role_id not in MANAGER_ROLES:
            raise PermissionDenied("only a manager or owner may publish an sop or policy")
        document = self.get_document(account, document_id)
        updated = self.repo.set_doc_type(document_id, account.tenant_id, doc_type)
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
            body={
                "document_id": document.document_id,
                "doc_type": updated.doc_type,
            },
        )
        return updated

    def list_blocks(self, account: Account, document_id: str) -> list[Block]:
        """The blocks of one document, in order."""
        self.get_document(account, document_id)
        return self.repo.list_blocks(document_id)

    def get_block(self, account: Account, document_id: str, block_id: str) -> Block:
        """One block, scoped to its document and the caller's tenant."""
        self.get_document(account, document_id)
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
        document = self.get_document(account, document_id)
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
        document = self.get_document(account, document_id)
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
        document = self.get_document(account, document_id)
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
        document = self.get_document(account, document_id)
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
        self.get_document(account, document_id)
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

    def snapshot_version(self, account: Account, document_id: str) -> Version:
        """Write the whole live block list into a new version row."""
        document = self.get_document(account, document_id)
        blocks = self.repo.list_blocks(document_id)
        snapshot = json.dumps([block.to_dict() for block in blocks])
        version_no = document.current_version
        version = self.repo.create_version(
            document_id=document_id,
            version_no=version_no,
            snapshot=snapshot,
            created_by=account.account_id,
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
            kind="version",
            body={
                "document_id": document.document_id,
                "version_id": version.version_id,
                "version_no": version.version_no,
                "block_count": len(blocks),
            },
        )
        return version

    def list_versions(self, account: Account, document_id: str) -> list[Version]:
        """Every version of one document, newest first."""
        self.get_document(account, document_id)
        return self.repo.list_versions(document_id)

    def get_version(self, account: Account, version_id: str) -> Version:
        """One version, scoped to a document the account can read."""
        version = self.repo.get_version(version_id, account.tenant_id)
        self.get_document(account, version.document_id)
        return version

    def restore_version(self, account: Account, document_id: str, version_no: int) -> Version:
        """Restore an old version WITHOUT rewriting it.

        A new version row is appended whose content equals the old snapshot,
        then the live block list is overwritten with that snapshot. The old
        version row keeps its bytes forever; the restore itself is recorded.
        """
        document = self.get_document(account, document_id)
        old = self.repo.get_version_by_no(document_id, version_no)
        blocks = json.loads(old.snapshot)
        new_version_no = document.current_version
        version = self.repo.create_version(
            document_id=document_id,
            version_no=new_version_no,
            snapshot=old.snapshot,
            created_by=account.account_id,
        )
        self.repo.replace_blocks(document_id, blocks, updated_by=account.account_id)
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
            kind="version",
            body={
                "document_id": document.document_id,
                "version_id": version.version_id,
                "version_no": version.version_no,
                "restored_from": version_no,
                "block_count": len(blocks),
            },
        )
        return version

    @staticmethod
    def _correlation_id() -> str:
        return f"doc-{uuid.uuid4().hex}"

    def _require_readable(self, account: Account, document: Document) -> None:
        if (
            document.doc_type == DOC_TYPE_NOTE
            and document.owner_account_id != account.account_id
            and account.role_id not in MANAGER_ROLES
        ):
            raise NotFoundError(f"no document {document.document_id!r} for this account")


def _validate_content(content: str) -> None:
    if content is None:
        raise ValueError("a block needs content")
    if len(content) > MAX_BLOCK_LENGTH:
        raise ValueError(f"a block holds at most {MAX_BLOCK_LENGTH} characters")
