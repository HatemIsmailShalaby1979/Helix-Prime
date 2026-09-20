"""The write and read surface for tasks, with the governance envelope.

The service owns two jobs:
1. CRUD on task and comment rows (delegated to the repository) plus the
   governed envelope (record_node) so every task write lands in the audit
   trail.
2. Notification: an assignee is notified exactly once on create-with-
   assignee and again when a new assignment changes the assignee. The
   notification uses the same NotificationService as messaging.

A status change is gated by a steward check: only the creator, the
current assignee, or a manager may change it. Comments are open to any
tenant member who holds tasks.use.
"""
from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone

from contracts.vocabulary import APP_RUNTIME_DATA_MODE
from helix_codex_app.db import record_node
from helix_codex_app.errors import PermissionDenied
from helix_codex_app.modules.notifications.service import MAX_PREVIEW, NotificationService
from helix_codex_app.modules.tasks.repository import (
    ALL_STATUSES,
    MANAGER_ROLES,
    Task,
    TaskComment,
    TasksRepository,
)
from helix_codex_app.security.accounts import Account

PROVENANCE_SOURCE = "helix_codex_app.tasks"
PROVENANCE_DATA_MODE = APP_RUNTIME_DATA_MODE


class TaskService:
    """Tasks, with the governance envelope and notification hooks."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self.repo = TasksRepository(conn)

    def create_task(
        self,
        account: Account,
        *,
        title: str,
        description: str = "",
        status: str = "open",
        priority: str = "medium",
        assignee_account_id: str | None = None,
        due_at: str | None = None,
    ) -> "Task":
        if not title or not title.strip():
            raise ValueError("a task needs a title")
        title = title.strip()
        if status not in ALL_STATUSES:
            raise ValueError(f"status must be one of {', '.join(ALL_STATUSES)}")
        task = self.repo.create_task(
            tenant_id=account.tenant_id,
            domain_id=account.domain_id,
            title=title,
            description=description,
            status=status,
            priority=priority,
            assignee_account_id=assignee_account_id,
            creator_account_id=account.account_id,
            due_at=due_at,
        )
        record_node(
            self.conn,
            tenant_id=account.tenant_id,
            client_id=account.client_id,
            domain_id=account.domain_id,
            correlation_id=f"task-{uuid.uuid4().hex}",
            classification="internal",
            nature="user_claim",
            created_by=account.account_id,
            provenance_source=PROVENANCE_SOURCE,
            provenance_data_mode=PROVENANCE_DATA_MODE,
            kind="task",
            body={
                "task_id": task.task_id,
                "title": task.title,
                "status": task.status,
                "priority": task.priority,
                "assignee_account_id": task.assignee_account_id,
                "due_at": task.due_at,
            },
        )
        if assignee_account_id and assignee_account_id != account.account_id:
            self._notify_assigned(account, task, assignee_account_id)
        return task

    def get_task(self, account: Account, task_id: str) -> "Task":
        return self.repo.get_task(task_id, account.tenant_id)

    def list_tasks(
        self,
        account: Account,
        filters: dict[str, str | None] | None = None,
    ) -> list["Task"]:
        filters = filters or {}
        return self.repo.list_tasks(
            tenant_id=account.tenant_id,
            q=filters.get("q"),
            status=filters.get("status"),
            assignee_account_id=filters.get("assignee"),
        )

    def update_task(
        self,
        account: Account,
        task_id: str,
        *,
        title: str | None = None,
        description: str | None = None,
        priority: str | None = None,
        due_at: str | None = None,
        assignee_account_id: str | None = None,
    ) -> "Task":
        task = self.get_task(account, task_id)
        self._require_steward(account, task)
        if assignee_account_id is not None:
            task = self.repo.assign_task(task_id, account.tenant_id, assignee_account_id)
            if assignee_account_id and assignee_account_id != account.account_id:
                self._notify_assigned(account, task, assignee_account_id)
            record_node(
                self.conn,
                tenant_id=account.tenant_id,
                client_id=account.client_id,
                domain_id=account.domain_id,
                correlation_id=f"task-{uuid.uuid4().hex}",
                classification="internal",
                nature="user_claim",
                created_by=account.account_id,
                provenance_source=PROVENANCE_SOURCE,
                provenance_data_mode=PROVENANCE_DATA_MODE,
                kind="task",
                body={
                    "task_id": task.task_id,
                    "assignee_account_id": task.assignee_account_id,
                },
            )
            return task
        if all(v is None for v in (title, description, priority, due_at)):
            return task
        task = self.repo.update_task(
            task_id,
            account.tenant_id,
            title=title,
            description=description,
            priority=priority,
            due_at=due_at,
        )
        record_node(
            self.conn,
            tenant_id=account.tenant_id,
            client_id=account.client_id,
            domain_id=account.domain_id,
            correlation_id=f"task-{uuid.uuid4().hex}",
            classification="internal",
            nature="user_claim",
            created_by=account.account_id,
            provenance_source=PROVENANCE_SOURCE,
            provenance_data_mode=PROVENANCE_DATA_MODE,
            kind="task",
            body={"task_id": task.task_id, "title": task.title},
        )
        return task

    def set_status(self, account: Account, task_id: str, status: str) -> "Task":
        if status not in ALL_STATUSES:
            raise ValueError(f"status must be one of {', '.join(ALL_STATUSES)}")
        task = self.get_task(account, task_id)
        self._require_steward(account, task)
        task = self.repo.set_status(task_id, account.tenant_id, status)
        record_node(
            self.conn,
            tenant_id=account.tenant_id,
            client_id=account.client_id,
            domain_id=account.domain_id,
            correlation_id=f"task-{uuid.uuid4().hex}",
            classification="internal",
            nature="user_claim",
            created_by=account.account_id,
            provenance_source=PROVENANCE_SOURCE,
            provenance_data_mode=PROVENANCE_DATA_MODE,
            kind="task",
            body={"task_id": task.task_id, "status": task.status},
        )
        return task

    def assign(self, account: Account, task_id: str, assignee_account_id: str) -> "Task":
        task = self.get_task(account, task_id)
        self._require_steward(account, task)
        old_assignee = task.assignee_account_id
        task = self.repo.assign_task(task_id, account.tenant_id, assignee_account_id)
        if assignee_account_id != old_assignee:
            record_node(
                self.conn,
                tenant_id=account.tenant_id,
                client_id=account.client_id,
                domain_id=account.domain_id,
                correlation_id=f"task-{uuid.uuid4().hex}",
                classification="internal",
                nature="user_claim",
                created_by=account.account_id,
                provenance_source=PROVENANCE_SOURCE,
                provenance_data_mode=PROVENANCE_DATA_MODE,
                kind="task",
                body={
                    "task_id": task.task_id,
                    "assignee_account_id": task.assignee_account_id,
                },
            )
            if assignee_account_id and assignee_account_id != account.account_id:
                self._notify_assigned(account, task, assignee_account_id)
        return task

    def add_comment(self, account: Account, task_id: str, body: str) -> TaskComment:
        if not body or not body.strip():
            raise ValueError("a comment needs a body")
        self.get_task(account, task_id)
        now = datetime.now(timezone.utc).isoformat()
        comment = self.repo.add_comment(
            task_id=task_id,
            comment_id=f"tcomment-{uuid.uuid4().hex}",
            account_id=account.account_id,
            body=body.strip(),
            created_at=now,
        )
        record_node(
            self.conn,
            tenant_id=account.tenant_id,
            client_id=account.client_id,
            domain_id=account.domain_id,
            correlation_id=f"task-{uuid.uuid4().hex}",
            classification="internal",
            nature="user_claim",
            created_by=account.account_id,
            provenance_source=PROVENANCE_SOURCE,
            provenance_data_mode=PROVENANCE_DATA_MODE,
            kind="task",
            body={
                "task_id": task_id,
                "comment_id": comment.comment_id,
                "body": comment.body[:MAX_PREVIEW],
            },
        )
        return comment

    def _require_steward(self, account: Account, task: "Task") -> None:
        if task.creator_account_id == account.account_id:
            return
        if task.assignee_account_id == account.account_id:
            return
        if account.role_id in MANAGER_ROLES:
            return
        raise PermissionDenied("only the creator, the assignee, or a manager may change this task")

    def _notify_assigned(self, account: Account, task: "Task", assignee_account_id: str) -> None:
        if not assignee_account_id or assignee_account_id == account.account_id:
            return
        NotificationService(self.conn).create(
            account_id=assignee_account_id,
            tenant_id=account.tenant_id,
            client_id=account.client_id,
            domain_id=account.domain_id,
            kind="task_assigned",
            title=f"Task assigned to you: {task.title}",
            body=(task.description or "")[:MAX_PREVIEW],
            link=f"/app/tasks/{task.task_id}",
            created_by=account.account_id,
            correlation_id=f"task-notif-{uuid.uuid4().hex}",
        )
