"""The storage layer for tasks and their comments.

Every query is scoped by tenant. A task carries a status (open, doing, done,
or the soft-delete state archived), a creator, and an optional assignee. Three
visible statuses appear on the board; archived tasks are excluded from the
default listing but can be retrieved with a filter. Comments are ordered
oldest-first so the conversation reads naturally.
"""
from __future__ import annotations

import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from helix_codex_app.errors import NotFoundError

OPEN = "open"
DOING = "doing"
DONE = "done"
ARCHIVED = "archived"
VISIBLE_STATUSES: tuple[str, ...] = (OPEN, DOING, DONE)
ALL_STATUSES: tuple[str, ...] = (OPEN, DOING, DONE, ARCHIVED)
MANAGER_ROLES: tuple[str, ...] = ("owner", "manager")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex}"


@dataclass(frozen=True)
class Task:
    """One task row."""

    task_id: str
    tenant_id: str
    domain_id: str | None
    title: str
    description: str
    status: str
    priority: str
    assignee_account_id: str | None
    creator_account_id: str
    due_at: str | None
    completed_at: str | None
    parent_task_id: str | None
    created_at: str
    updated_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "tenant_id": self.tenant_id,
            "domain_id": self.domain_id,
            "title": self.title,
            "description": self.description,
            "status": self.status,
            "priority": self.priority,
            "assignee_account_id": self.assignee_account_id,
            "creator_account_id": self.creator_account_id,
            "due_at": self.due_at,
            "completed_at": self.completed_at,
            "parent_task_id": self.parent_task_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass(frozen=True)
class TaskComment:
    """One comment on a task."""

    comment_id: str
    task_id: str
    account_id: str
    body: str
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "comment_id": self.comment_id,
            "task_id": self.task_id,
            "account_id": self.account_id,
            "body": self.body,
            "created_at": self.created_at,
        }


class TasksRepository:
    """The read and write surface for tasks and task comments."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def create_task(
        self,
        *,
        tenant_id: str,
        domain_id: str | None,
        title: str,
        description: str,
        status: str,
        priority: str,
        assignee_account_id: str | None,
        creator_account_id: str,
        due_at: str | None,
    ) -> Task:
        task_id = _new_id("task")
        now = _now()
        self.conn.execute(
            """
            INSERT INTO tasks (
                task_id, tenant_id, domain_id, title, description, status,
                priority, assignee_account_id, creator_account_id, due_at,
                completed_at, parent_task_id, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, ?, ?)
            """,
            (
                task_id,
                tenant_id,
                domain_id,
                title,
                description,
                status,
                priority,
                assignee_account_id,
                creator_account_id,
                due_at,
                now,
                now,
            ),
        )
        self.conn.commit()
        return self.get_task(task_id, tenant_id)

    def get_task(self, task_id: str, tenant_id: str) -> Task:
        row = self.conn.execute(
            """
            SELECT task_id, tenant_id, domain_id, title, description, status,
                   priority, assignee_account_id, creator_account_id, due_at,
                   completed_at, parent_task_id, created_at, updated_at
            FROM tasks WHERE task_id = ? AND tenant_id = ?
            """,
            (task_id, tenant_id),
        ).fetchone()
        if row is None:
            raise NotFoundError("task not found")
        return _task_from_row(row)

    def list_tasks(
        self,
        *,
        tenant_id: str,
        q: str | None = None,
        status: str | None = None,
        assignee_account_id: str | None = None,
        include_archived: bool = False,
    ) -> list[Task]:
        sql = """
            SELECT task_id, tenant_id, domain_id, title, description, status,
                   priority, assignee_account_id, creator_account_id, due_at,
                   completed_at, parent_task_id, created_at, updated_at
            FROM tasks
            WHERE tenant_id = ?
        """
        params: list[Any] = [tenant_id]
        if status:
            sql += " AND status = ?"
            params.append(status)
        elif not include_archived:
            sql += " AND status != ?"
            params.append(ARCHIVED)
        if q:
            sql += " AND title LIKE ?"
            params.append(f"%{q}%")
        if assignee_account_id:
            sql += " AND assignee_account_id = ?"
            params.append(assignee_account_id)
        sql += " ORDER BY updated_at DESC, rowid DESC"
        rows = self.conn.execute(sql, params).fetchall()
        return [_task_from_row(row) for row in rows]

    def update_task(
        self,
        task_id: str,
        tenant_id: str,
        *,
        title: str | None = None,
        description: str | None = None,
        priority: str | None = None,
        due_at: str | None = None,
    ) -> Task:
        """Update the mutable fields of a task.

        Each field is a separate static UPDATE, so no statement is
        assembled from caller data.
        """
        now = _now()
        if title is not None:
            self.conn.execute(
                "UPDATE tasks SET title = ?, updated_at = ? WHERE task_id = ? AND tenant_id = ?",
                (title, now, task_id, tenant_id),
            )
        if description is not None:
            self.conn.execute(
                "UPDATE tasks SET description = ?, updated_at = ? WHERE task_id = ? AND tenant_id = ?",
                (description, now, task_id, tenant_id),
            )
        if priority is not None:
            self.conn.execute(
                "UPDATE tasks SET priority = ?, updated_at = ? WHERE task_id = ? AND tenant_id = ?",
                (priority, now, task_id, tenant_id),
            )
        if due_at is not None:
            self.conn.execute(
                "UPDATE tasks SET due_at = ?, updated_at = ? WHERE task_id = ? AND tenant_id = ?",
                (due_at, now, task_id, tenant_id),
            )
        self.conn.commit()
        return self.get_task(task_id, tenant_id)

    def set_status(self, task_id: str, tenant_id: str, status: str) -> Task:
        completed_at = _now() if status == DONE else None
        self.conn.execute(
            "UPDATE tasks SET status = ?, completed_at = ?, updated_at = ? "
            "WHERE task_id = ? AND tenant_id = ?",
            (status, completed_at, _now(), task_id, tenant_id),
        )
        self.conn.commit()
        return self.get_task(task_id, tenant_id)

    def assign_task(self, task_id: str, tenant_id: str, assignee_account_id: str | None) -> Task:
        self.conn.execute(
            "UPDATE tasks SET assignee_account_id = ?, updated_at = ? "
            "WHERE task_id = ? AND tenant_id = ?",
            (assignee_account_id, _now(), task_id, tenant_id),
        )
        self.conn.commit()
        return self.get_task(task_id, tenant_id)

    def add_comment(
        self,
        *,
        task_id: str,
        comment_id: str,
        account_id: str,
        body: str,
        created_at: str,
    ) -> TaskComment:
        self.conn.execute(
            "INSERT INTO task_comments (comment_id, task_id, account_id, body, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (comment_id, task_id, account_id, body, created_at),
        )
        self.conn.commit()
        row = self.conn.execute(
            "SELECT comment_id, task_id, account_id, body, created_at "
            "FROM task_comments WHERE comment_id = ?",
            (comment_id,),
        ).fetchone()
        return _comment_from_row(row)

    def list_comments(self, task_id: str) -> list[TaskComment]:
        rows = self.conn.execute(
            "SELECT comment_id, task_id, account_id, body, created_at "
            "FROM task_comments WHERE task_id = ? ORDER BY rowid ASC",
            (task_id,),
        ).fetchall()
        return [_comment_from_row(row) for row in rows]


def _task_from_row(row: sqlite3.Row) -> Task:
    return Task(
        task_id=row["task_id"],
        tenant_id=row["tenant_id"],
        domain_id=row["domain_id"],
        title=row["title"],
        description=row["description"],
        status=row["status"],
        priority=row["priority"],
        assignee_account_id=row["assignee_account_id"],
        creator_account_id=row["creator_account_id"],
        due_at=row["due_at"],
        completed_at=row["completed_at"],
        parent_task_id=row["parent_task_id"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _comment_from_row(row: sqlite3.Row) -> TaskComment:
    return TaskComment(
        comment_id=row["comment_id"],
        task_id=row["task_id"],
        account_id=row["account_id"],
        body=row["body"],
        created_at=row["created_at"],
    )
