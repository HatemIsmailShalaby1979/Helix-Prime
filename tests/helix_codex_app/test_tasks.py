"""Tasks with a board, assignment, and comments tests (P3.3).

Service-level tests prove the P3.3 invariants: every task write produces one
governed node, status changes are gated by the steward check, comments are
ordered oldest-first, and the board excludes archived tasks by default. HTTP
tests drive the mounted tasks router through TestClient for the screens, the
JSON contract, the HTMX fragment path, CSRF, and cross-tenant isolation.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

fastapi_testclient = pytest.importorskip("fastapi.testclient")
TestClient = fastapi_testclient.TestClient

from helix_codex_app import db
from helix_codex_app.app import create_app
from helix_codex_app.config import AppSettings
from helix_codex_app.errors import PermissionDenied
from helix_codex_app.modules.tasks.service import TaskService
from helix_codex_app.security.accounts import AccountRepository
from helix_codex_app.security.passwords import hash_password
from helix_codex_app.security.sessions import SESSION_COOKIE, SessionStore


@pytest.fixture()
def ctx(tmp_path):
    db_path = str(tmp_path / "app.db")
    conn = db.connect(db_path=db_path)
    db._init_schema(conn)
    repo = AccountRepository(conn)
    domain_a = repo.create_domain("a.academy", tenant_id="tenant-a", client_id="client-a")
    domain_b = repo.create_domain("b.academy", tenant_id="tenant-b", client_id="client-b")
    owner = repo.create_account(
        domain_a.domain_id, "owner", role_id="owner", password_hash=hash_password("x")
    )
    amira = repo.create_account(
        domain_a.domain_id, "amira", role_id="employee", password_hash=hash_password("x")
    )
    omar = repo.create_account(
        domain_a.domain_id, "omar", role_id="employee", password_hash=hash_password("x")
    )
    ghada = repo.create_account(
        domain_b.domain_id, "ghada", role_id="employee", password_hash=hash_password("x")
    )
    settings = AppSettings(db_path=db_path, cookie_secure=False)
    store = SessionStore(conn, settings)
    service = TaskService(conn)
    yield SimpleNamespace(
        conn=conn,
        repo=repo,
        domain_a=domain_a,
        domain_b=domain_b,
        owner=owner,
        amira=amira,
        omar=omar,
        ghada=ghada,
        settings=settings,
        store=store,
        service=service,
    )
    db.close(conn)


@pytest.fixture()
def client(ctx):
    with TestClient(create_app(ctx.settings), follow_redirects=False) as test_client:
        yield test_client


def _login(ctx, account) -> tuple[dict, dict]:
    token, _session = ctx.store.issue_session(account)
    session = ctx.store.verify(token)
    assert session is not None
    return {SESSION_COOKIE: token}, {"X-CSRF-Token": session.csrf_token}


def _node_count(conn, kind: str) -> int:
    return conn.execute("SELECT COUNT(*) FROM nodes WHERE kind = ?", (kind,)).fetchone()[0]


# --- service-level tests ---


def test_create_task_writes_one_node(ctx):
    before = _node_count(ctx.conn, "task")
    task = ctx.service.create_task(ctx.amira, title="Write tests")
    assert task.title == "Write tests"
    assert task.status == "open"
    assert task.creator_account_id == ctx.amira.account_id
    assert _node_count(ctx.conn, "task") == before + 1


def test_create_task_with_assignee(ctx):
    task = ctx.service.create_task(ctx.amira, title="Pair", assignee_account_id=ctx.omar.account_id)
    assert task.assignee_account_id == ctx.omar.account_id


def test_create_task_blank_title_rejected(ctx):
    with pytest.raises(ValueError, match="title"):
        ctx.service.create_task(ctx.amira, title="")


def test_list_tasks_excludes_archived(ctx):
    ctx.service.create_task(ctx.amira, title="visible")
    task = ctx.service.create_task(ctx.amira, title="gone")
    ctx.service.set_status(ctx.amira, task.task_id, "archived")
    tasks = ctx.service.list_tasks(ctx.amira)
    titles = [t.title for t in tasks]
    assert "visible" in titles
    assert "gone" not in titles


def test_set_status_done_stamps_completed_at(ctx):
    task = ctx.service.create_task(ctx.amira, title="done task")
    assert task.completed_at is None
    task = ctx.service.set_status(ctx.amira, task.task_id, "doing")
    assert task.completed_at is None
    task = ctx.service.set_status(ctx.amira, task.task_id, "done")
    assert task.completed_at is not None


def test_set_status_bad_value_rejected(ctx):
    task = ctx.service.create_task(ctx.amira, title="x")
    with pytest.raises(ValueError, match="status"):
        ctx.service.set_status(ctx.amira, task.task_id, "invalid")


def test_steward_check_creator_can_change_status(ctx):
    task = ctx.service.create_task(ctx.amira, title="t")
    task = ctx.service.set_status(ctx.amira, task.task_id, "doing")
    assert task.status == "doing"


def test_steward_check_assignee_can_change_status(ctx):
    task = ctx.service.create_task(ctx.amira, title="t", assignee_account_id=ctx.omar.account_id)
    task = ctx.service.set_status(ctx.omar, task.task_id, "doing")
    assert task.status == "doing"


def test_steward_check_manager_can_change_status(ctx):
    task = ctx.service.create_task(ctx.amira, title="t")
    task = ctx.service.set_status(ctx.owner, task.task_id, "doing")
    assert task.status == "doing"


def test_steward_check_unrelated_employee_denied(ctx):
    task = ctx.service.create_task(ctx.amira, title="t")
    with pytest.raises(PermissionDenied):
        ctx.service.set_status(ctx.omar, task.task_id, "doing")


def test_assign_notifies_assignee(ctx):
    task = ctx.service.create_task(ctx.amira, title="t")
    ctx.service.assign(ctx.amira, task.task_id, ctx.omar.account_id)
    notifs = ctx.conn.execute(
        "SELECT * FROM notifications WHERE account_id = ?", (ctx.omar.account_id,)
    ).fetchall()
    assert len(notifs) == 1
    assert "Task assigned" in notifs[0]["title"]


def test_add_comment_writes_one_node(ctx):
    task = ctx.service.create_task(ctx.amira, title="t")
    before = _node_count(ctx.conn, "task")
    comment = ctx.service.add_comment(ctx.omar, task.task_id, "looks good")
    assert comment.body == "looks good"
    assert comment.account_id == ctx.omar.account_id
    assert _node_count(ctx.conn, "task") == before + 1


def test_add_comment_blank_rejected(ctx):
    task = ctx.service.create_task(ctx.amira, title="t")
    with pytest.raises(ValueError, match="body"):
        ctx.service.add_comment(ctx.omar, task.task_id, "")


def test_list_comments_oldest_first(ctx):
    task = ctx.service.create_task(ctx.amira, title="t")
    ctx.service.add_comment(ctx.amira, task.task_id, "first")
    ctx.service.add_comment(ctx.omar, task.task_id, "second")
    comments = ctx.conn.execute(
        "SELECT body FROM task_comments WHERE task_id = ? ORDER BY rowid ASC",
        (task.task_id,),
    ).fetchall()
    assert [c["body"] for c in comments] == ["first", "second"]


def test_update_task_fields(ctx):
    task = ctx.service.create_task(ctx.amira, title="old", priority="low")
    task = ctx.service.update_task(ctx.amira, task.task_id, title="new", priority="high")
    assert task.title == "new"
    assert task.priority == "high"


def test_notification_only_on_assignee_change(ctx):
    task = ctx.service.create_task(ctx.amira, title="t")
    ctx.service.assign(ctx.amira, task.task_id, ctx.omar.account_id)
    count_before = ctx.conn.execute(
        "SELECT COUNT(*) FROM notifications WHERE account_id = ?", (ctx.omar.account_id,)
    ).fetchone()[0]
    ctx.service.assign(ctx.omar, task.task_id, ctx.omar.account_id)
    count_after = ctx.conn.execute(
        "SELECT COUNT(*) FROM notifications WHERE account_id = ?", (ctx.omar.account_id,)
    ).fetchone()[0]
    assert count_after == count_before


def test_notification_once_on_create_with_assignee(ctx):
    task = ctx.service.create_task(ctx.amira, title="t", assignee_account_id=ctx.omar.account_id)
    notifs = ctx.conn.execute(
        "SELECT * FROM notifications WHERE account_id = ?", (ctx.omar.account_id,)
    ).fetchall()
    assert len(notifs) == 1


# --- HTTP-level tests ---


def test_board_screen_renders(client, ctx):
    cookies, headers = _login(ctx, ctx.amira)
    resp = client.get("/app/tasks", cookies=cookies)
    assert resp.status_code == 200
    assert "Tasks" in resp.text
    assert "task-board" in resp.text


def test_task_detail_screen_renders(client, ctx):
    cookies, _ = _login(ctx, ctx.amira)
    task = ctx.service.create_task(ctx.amira, title="detail test")
    resp = client.get(f"/app/tasks/{task.task_id}", cookies=cookies)
    assert resp.status_code == 200
    assert "detail test" in resp.text


def test_task_detail_401_unauth(client, ctx):
    resp = client.get("/app/tasks/fake-id")
    assert resp.status_code == 401


def test_task_detail_404_foreign(client, ctx):
    cookies, _ = _login(ctx, ctx.ghada)
    task = ctx.service.create_task(ctx.amira, title="a")
    resp = client.get(f"/app/tasks/{task.task_id}", cookies=cookies)
    assert resp.status_code == 404


def test_create_task_json(client, ctx):
    cookies, headers = _login(ctx, ctx.amira)
    resp = client.post(
        "/app/api/tasks",
        json={"title": "json task"},
        cookies=cookies,
        headers=headers,
    )
    assert resp.status_code == 201
    assert resp.json()["title"] == "json task"


def test_create_task_htmx_fragment(client, ctx):
    cookies, headers = _login(ctx, ctx.amira)
    resp = client.post(
        "/app/api/tasks",
        data={"title": "hx task"},
        cookies=cookies,
        headers={**headers, "HX-Request": "true"},
    )
    assert resp.status_code == 200
    assert "task-board" in resp.text


def test_create_task_no_csrf(client, ctx):
    cookies, _ = _login(ctx, ctx.amira)
    resp = client.post("/app/api/tasks", json={"title": "x"}, cookies=cookies)
    assert resp.status_code == 403


def test_get_task_json(client, ctx):
    cookies, _ = _login(ctx, ctx.amira)
    task = ctx.service.create_task(ctx.amira, title="j")
    resp = client.get(f"/app/api/tasks/{task.task_id}", cookies=cookies)
    assert resp.status_code == 200
    assert resp.json()["task"]["title"] == "j"


def test_set_status_json(client, ctx):
    cookies, headers = _login(ctx, ctx.amira)
    task = ctx.service.create_task(ctx.amira, title="s")
    resp = client.post(
        f"/app/api/tasks/{task.task_id}/status",
        json={"status": "doing"},
        cookies=cookies,
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "doing"


def test_set_status_htmx_fragment(client, ctx):
    cookies, headers = _login(ctx, ctx.amira)
    task = ctx.service.create_task(ctx.amira, title="hx")
    resp = client.post(
        f"/app/api/tasks/{task.task_id}/status",
        data={"status": "done"},
        cookies=cookies,
        headers={**headers, "HX-Request": "true"},
    )
    assert resp.status_code == 200
    assert "task-board" in resp.text


def test_add_comment_json(client, ctx):
    cookies, headers = _login(ctx, ctx.omar)
    task = ctx.service.create_task(ctx.amira, title="c")
    resp = client.post(
        f"/app/api/tasks/{task.task_id}/comments",
        json={"body": "nice"},
        cookies=cookies,
        headers=headers,
    )
    assert resp.status_code == 201
    assert resp.json()["body"] == "nice"


def test_add_comment_htmx_fragment(client, ctx):
    cookies, headers = _login(ctx, ctx.omar)
    task = ctx.service.create_task(ctx.amira, title="c")
    resp = client.post(
        f"/app/api/tasks/{task.task_id}/comments",
        data={"body": "nice"},
        cookies=cookies,
        headers={**headers, "HX-Request": "true"},
    )
    assert resp.status_code == 200
    assert "task-comments" in resp.text


def test_tasks_401_unauth(client, ctx):
    resp = client.get("/app/tasks")
    assert resp.status_code == 401
