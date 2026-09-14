"""The tasks surface: the board, task detail, comments, and the API.

GET routes render the board and the detail screen; the mutating routes
write one governed node per action through TaskService. The board
supports drag-and-drop (Alpine.js) on desktop and a status select on
mobile. Every mutating route accepts a JSON body or an HTMX urlencoded
form through the same _payload() helper used by the other modules.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse

from helix_codex_app.db import close, connect
from helix_codex_app.errors import NotFoundError, PermissionDenied
from helix_codex_app.modules.tasks.service import TaskService
from helix_codex_app.security.accounts import Account, AccountRepository
from helix_codex_app.security.guard import current_account, require_csrf, require_permission
from helix_codex_app.templating import render

tasks_router = APIRouter(
    prefix="/app",
    dependencies=[Depends(current_account), Depends(require_permission("tasks.use"))],
)


@tasks_router.get("/tasks", response_model=None)
def tasks_list_screen(request: Request) -> HTMLResponse:
    """The task board with three columns: open, doing, done."""
    account = _account(request)
    q = request.query_params.get("q") or ""
    conn = _conn(request)
    try:
        tasks = TaskService(conn).list_tasks(account, {"q": q})
        members = {
            a.account_id: a.display_name or a.username
            for a in AccountRepository(conn).list_accounts(account.domain_id)
        }
    finally:
        close(conn)
    context = {
        "account": account,
        "tasks": tasks,
        "members": members,
        "q": q,
    }
    if request.headers.get("hx-request") == "true":
        return render(request, "partials/task_board.html", context)
    return render(request, "tasks.html", {"active_nav": "tasks", **context})


@tasks_router.get("/tasks/{task_id}", response_model=None)
def task_detail_screen(request: Request, task_id: str) -> HTMLResponse:
    """One task with its description, assignment, and comments."""
    account = _account(request)
    conn = _conn(request)
    try:
        service = TaskService(conn)
        task = service.get_task(account, task_id)
        comments = conn.execute(
            "SELECT comment_id, task_id, account_id, body, created_at "
            "FROM task_comments WHERE task_id = ? ORDER BY rowid ASC",
            (task_id,),
        ).fetchall()
        members = {
            a.account_id: a.display_name or a.username
            for a in AccountRepository(conn).list_accounts(account.domain_id)
        }
    finally:
        close(conn)
    return render(
        request,
        "task_detail.html",
        {
            "active_nav": "tasks",
            "account": account,
            "task": task,
            "comments": comments,
            "members": members,
        },
    )


@tasks_router.post(
    "/api/tasks",
    response_model=None,
    dependencies=[Depends(require_csrf), Depends(require_permission("tasks.use"))],
)
async def create_task_route(request: Request) -> JSONResponse | HTMLResponse:
    """Create a task and record one governed node."""
    account = _account(request)
    try:
        raw = await _payload(request)
        title = str(raw.get("title", "")).strip()
        description = str(raw.get("description", "")).strip()
        priority = str(raw.get("priority", "medium")).strip()
        due_at = str(raw.get("due_at", "")).strip() or None
        assignee_account_id = str(raw.get("assignee_account_id", "")).strip() or None
        if not title:
            return JSONResponse({"error": "a task needs a title"}, status_code=400)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    conn = _conn(request)
    hx_fragment = None
    try:
        service = TaskService(conn)
        task = service.create_task(
            account,
            title=title,
            description=description,
            priority=priority,
            due_at=due_at,
            assignee_account_id=assignee_account_id,
        )
        if request.headers.get("hx-request") == "true":
            tasks = service.list_tasks(account)
            members = {
                a.account_id: a.display_name or a.username
                for a in AccountRepository(conn).list_accounts(account.domain_id)
            }
            hx_fragment = render(
                request,
                "partials/task_board.html",
                {"account": account, "tasks": tasks, "members": members, "q": ""},
            )
    except PermissionDenied as exc:
        return JSONResponse({"error": str(exc)}, status_code=403)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    finally:
        close(conn)
    if hx_fragment is not None:
        return hx_fragment
    return JSONResponse(task.to_dict(), status_code=201)


@tasks_router.get("/api/tasks/{task_id}", response_model=None)
def get_task_route(request: Request, task_id: str) -> JSONResponse:
    """One task with its comments, tenant scoped."""
    account = _account(request)
    conn = _conn(request)
    try:
        service = TaskService(conn)
        task = service.get_task(account, task_id)
        comments = [
            dict(c)
            for c in conn.execute(
                "SELECT comment_id, task_id, account_id, body, created_at "
                "FROM task_comments WHERE task_id = ? ORDER BY rowid ASC",
                (task_id,),
            ).fetchall()
        ]
    except NotFoundError as exc:
        return JSONResponse({"error": str(exc)}, status_code=404)
    finally:
        close(conn)
    return JSONResponse({"task": task.to_dict(), "comments": comments})


@tasks_router.put(
    "/api/tasks/{task_id}",
    response_model=None,
    dependencies=[Depends(require_csrf), Depends(require_permission("tasks.use"))],
)
async def update_task_route(request: Request, task_id: str) -> JSONResponse:
    """Update a task's title, description, priority, due date, or assignee."""
    account = _account(request)
    try:
        raw = await _payload(request)
        title = str(raw.get("title", "")).strip() or None
        description = raw.get("description")
        if description is not None:
            description = str(description).strip()
        priority = str(raw.get("priority", "")).strip() or None
        due_at = str(raw.get("due_at", "")).strip() or None
        assignee_account_id = raw.get("assignee_account_id")
        if assignee_account_id is not None:
            assignee_account_id = str(assignee_account_id).strip() or None
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    conn = _conn(request)
    try:
        task = TaskService(conn).update_task(
            account,
            task_id,
            title=title,
            description=description,
            priority=priority,
            due_at=due_at,
            assignee_account_id=assignee_account_id,
        )
    except NotFoundError as exc:
        return JSONResponse({"error": str(exc)}, status_code=404)
    except PermissionDenied as exc:
        return JSONResponse({"error": str(exc)}, status_code=403)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    finally:
        close(conn)
    return JSONResponse(task.to_dict())


@tasks_router.post(
    "/api/tasks/{task_id}/status",
    response_model=None,
    dependencies=[Depends(require_csrf), Depends(require_permission("tasks.use"))],
)
async def set_status_route(request: Request, task_id: str) -> JSONResponse | HTMLResponse:
    """Change the task's status and record one governed node."""
    account = _account(request)
    try:
        raw = await _payload(request)
        status = str(raw.get("status", "")).strip()
        if not status:
            return JSONResponse({"error": "status is required"}, status_code=400)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    conn = _conn(request)
    hx_fragment = None
    try:
        service = TaskService(conn)
        task = service.set_status(account, task_id, status)
        if request.headers.get("hx-request") == "true":
            tasks = service.list_tasks(account)
            members = {
                a.account_id: a.display_name or a.username
                for a in AccountRepository(conn).list_accounts(account.domain_id)
            }
            hx_fragment = render(
                request,
                "partials/task_board.html",
                {"account": account, "tasks": tasks, "members": members, "q": ""},
            )
    except NotFoundError as exc:
        return JSONResponse({"error": str(exc)}, status_code=404)
    except PermissionDenied as exc:
        return JSONResponse({"error": str(exc)}, status_code=403)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    finally:
        close(conn)
    if hx_fragment is not None:
        return hx_fragment
    return JSONResponse(task.to_dict())


@tasks_router.post(
    "/api/tasks/{task_id}/comments",
    response_model=None,
    dependencies=[Depends(require_csrf), Depends(require_permission("tasks.use"))],
)
async def add_comment_route(request: Request, task_id: str) -> JSONResponse | HTMLResponse:
    """Add a comment to a task."""
    account = _account(request)
    try:
        raw = await _payload(request)
        body = str(raw.get("body", "")).strip()
        if not body:
            return JSONResponse({"error": "a comment needs a body"}, status_code=400)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    conn = _conn(request)
    hx_fragment = None
    try:
        service = TaskService(conn)
        comment = service.add_comment(account, task_id, body)
        if request.headers.get("hx-request") == "true":
            comments = conn.execute(
                "SELECT comment_id, task_id, account_id, body, created_at "
                "FROM task_comments WHERE task_id = ? ORDER BY rowid ASC",
                (task_id,),
            ).fetchall()
            members = {
                a.account_id: a.display_name or a.username
                for a in AccountRepository(conn).list_accounts(account.domain_id)
            }
            hx_fragment = render(
                request,
                "partials/task_detail_comments.html",
                {"account": account, "comments": comments, "members": members},
            )
    except NotFoundError as exc:
        return JSONResponse({"error": str(exc)}, status_code=404)
    except PermissionDenied as exc:
        return JSONResponse({"error": str(exc)}, status_code=403)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    finally:
        close(conn)
    if hx_fragment is not None:
        return hx_fragment
    return JSONResponse(comment.to_dict(), status_code=201)


async def _payload(request: Request) -> dict[str, Any]:
    """The request body as a mapping, from JSON or an HTMX urlencoded form."""
    content_type = request.headers.get("content-type", "")
    if content_type.startswith("application/json"):
        body = await request.json()
        return body if isinstance(body, dict) else {}
    form = await request.form()
    return {key: value for key, value in form.multi_items()}


def _account(request: Request) -> Account:
    return request.state.account


def _conn(request: Request):
    return connect(db_path=request.app.state.settings.db_path)
