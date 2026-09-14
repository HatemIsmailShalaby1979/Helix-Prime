"""Chat screens, the messaging JSON API, and the conversation SSE stream.

The HTML screens are mobile-first: a conversation list, a thread that
appends messages as they arrive, and a composer pinned above the keyboard.
The JSON endpoints serve the wire contract the P2.1 schemas pinned, and the
SSE stream replays the parent EventBus for one conversation. Membership is
checked in every route; a non-member finds no conversation anywhere, and on
the stream the refusal is a 403 rather than a 404 so it carries no content.
Mutating routes read a JSON body or an HTMX urlencoded form, so the same
endpoint serves a pure client and the shell's own composer.
"""
from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse

from helix_codex_app.db import close, connect
from helix_codex_app.errors import NotFoundError, PermissionDenied
from helix_codex_app.integration.sse_bridge import encode, publish, subscribe, unsubscribe
from helix_codex_app.modules.messaging.repository import MessagingRepository
from helix_codex_app.modules.messaging.schemas import (
    ConversationOut,
    CreateDirectRequest,
    CreateGroupRequest,
    MessageOut,
    MessagePage,
    SendMessageRequest,
)
from helix_codex_app.modules.messaging.service import MessagingService
from helix_codex_app.security.accounts import Account, AccountRepository
from helix_codex_app.security.guard import current_account, require_csrf
from helix_codex_app.templating import render

messaging_router = APIRouter(prefix="/app", dependencies=[Depends(current_account)])

_HEARTBEAT_SECONDS = 15


@messaging_router.get("/chat", response_model=None)
def chat_list_screen(request: Request) -> HTMLResponse:
    """The conversation list, plus a way to start a new chat."""
    account = _account(request)
    conn = _conn(request)
    try:
        service = MessagingService(conn)
        repo = AccountRepository(conn)
        conversations = service.list_conversations(account)
        peers = [
            p for p in repo.list_accounts(account.domain_id) if p.account_id != account.account_id
        ]
        titles = _conversation_titles(conn, service, repo, conversations, account)
    finally:
        close(conn)
    return render(
        request,
        "chat/list.html",
        {
            "active_nav": "chat",
            "account": account,
            "conversations": [ConversationOut.from_conversation(c) for c in conversations],
            "titles": titles,
            "peers": peers,
        },
    )


@messaging_router.get("/chat/{conversation_id}", response_model=None)
def chat_thread_screen(request: Request, conversation_id: str) -> HTMLResponse:
    """One thread: its messages oldest-first, ready to stream new ones."""
    account = _account(request)
    conn = _conn(request)
    try:
        service = MessagingService(conn)
        conversation = service.get_conversation(account, conversation_id)
        messages = service.list_messages(account, conversation_id, limit=200)
        senders = _sender_names(conn, messages)
    finally:
        close(conn)
    return render(
        request,
        "chat/thread.html",
        {
            "active_nav": "chat",
            "account": account,
            "conversation": ConversationOut.from_conversation(conversation),
            "messages": [MessageOut.from_message(m) for m in reversed(messages)],
            "senders": senders,
        },
    )


@messaging_router.get("/api/conversations", response_model=None)
def list_conversations(request: Request) -> JSONResponse:
    """Every conversation the caller belongs to, newest activity first."""
    account = _account(request)
    conn = _conn(request)
    try:
        conversations = MessagingService(conn).list_conversations(account)
    finally:
        close(conn)
    return JSONResponse(
        [ConversationOut.from_conversation(c).model_dump(mode="json") for c in conversations]
    )


@messaging_router.post(
    "/api/conversations",
    response_model=None,
    dependencies=[Depends(require_csrf)],
)
async def create_conversation(request: Request) -> JSONResponse | HTMLResponse:
    """Start a direct conversation with one account or a group with many."""
    account = _account(request)
    try:
        raw = await _payload(request)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    conn = _conn(request)
    hx_fragment = None
    try:
        service = MessagingService(conn)
        repo = AccountRepository(conn)
        try:
            if "account_id" in raw:
                parsed = CreateDirectRequest.model_validate(raw)
                other = repo.get_account_by_id(parsed.account_id)
                if other is None or other.tenant_id != account.tenant_id:
                    return JSONResponse({"error": "no such account"}, status_code=404)
                conversation = service.create_direct(account, other)
            else:
                group_raw = dict(raw)
                member_ids = group_raw.get("member_ids")
                if isinstance(member_ids, (str, int)):
                    group_raw["member_ids"] = [member_ids]
                parsed = CreateGroupRequest.model_validate(group_raw)
                members = [repo.get_account_by_id(mid) for mid in parsed.member_ids]
                if any(member is None for member in members):
                    return JSONResponse(
                        {"error": "a member account does not exist"}, status_code=404
                    )
                conversation = service.create_group(
                    account,
                    parsed.name,
                    [member for member in members if member is not None],
                )
        except ValueError as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)
        if request.headers.get("hx-request") == "true":
            conversations = service.list_conversations(account)
            peers = [
                p
                for p in repo.list_accounts(account.domain_id)
                if p.account_id != account.account_id
            ]
            titles = _conversation_titles(conn, service, repo, conversations, account)
            hx_fragment = render(
                request,
                "partials/chat_list.html",
                {
                    "account": account,
                    "conversations": [ConversationOut.from_conversation(c) for c in conversations],
                    "titles": titles,
                    "peers": peers,
                },
            )
    finally:
        close(conn)
    if hx_fragment is not None:
        return hx_fragment
    return JSONResponse(
        ConversationOut.from_conversation(conversation).model_dump(mode="json"),
        status_code=201,
    )


@messaging_router.get("/api/conversations/{conversation_id}/messages", response_model=None)
def list_messages_route(request: Request, conversation_id: str) -> JSONResponse:
    """A newest-first page of one conversation, scoped to a member."""
    account = _account(request)
    before = request.query_params.get("before")
    try:
        limit = int(request.query_params.get("limit") or 50)
    except ValueError:
        return JSONResponse({"error": "limit must be an integer"}, status_code=400)
    conn = _conn(request)
    try:
        messages = MessagingService(conn).list_messages(
            account, conversation_id, before=before, limit=limit
        )
    except NotFoundError as exc:
        return JSONResponse({"error": str(exc)}, status_code=404)
    finally:
        close(conn)
    out = [MessageOut.from_message(m) for m in messages]
    return JSONResponse(
        MessagePage(messages=out, next_before=out[-1].created_at if out else None).model_dump(
            mode="json"
        )
    )


@messaging_router.post(
    "/api/conversations/{conversation_id}/messages",
    response_model=None,
    dependencies=[Depends(require_csrf)],
)
async def send_message_route(request: Request, conversation_id: str) -> JSONResponse | HTMLResponse:
    """Store one message, write its governed node, then stream it to members."""
    account = _account(request)
    try:
        raw = await _payload(request)
        parsed = SendMessageRequest.model_validate(raw)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    conn = _conn(request)
    try:
        message = MessagingService(conn).send_message(account, conversation_id, parsed.body)
    except NotFoundError as exc:
        return JSONResponse({"error": str(exc)}, status_code=404)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    finally:
        close(conn)
    message_out = MessageOut.from_message(message)
    publish(conversation_id, "message", message_out.model_dump(mode="json"))
    if request.headers.get("hx-request") == "true":
        return render(
            request,
            "partials/message_row.html",
            {"message": message_out, "account": account, "senders": {}},
        )
    return JSONResponse(message_out.model_dump(mode="json"), status_code=201)


@messaging_router.post(
    "/api/conversations/{conversation_id}/read",
    response_model=None,
    dependencies=[Depends(require_csrf)],
)
def mark_read_route(request: Request, conversation_id: str) -> JSONResponse:
    """Stamp the caller's read position. Only their own row moves."""
    account = _account(request)
    conn = _conn(request)
    try:
        service = MessagingService(conn)
        service.get_conversation(account, conversation_id)
        service.mark_read(account, conversation_id)
    except NotFoundError as exc:
        return JSONResponse({"error": str(exc)}, status_code=404)
    finally:
        close(conn)
    return JSONResponse({"ok": True})


@messaging_router.get("/api/conversations/{conversation_id}/stream")
async def conversation_stream(request: Request, conversation_id: str) -> StreamingResponse:
    """The live frame stream for one conversation, membership checked first.

    Non-members get a 403 here, not a 404, so an observer cannot learn that
    a conversation exists. The membership gate runs before the stream opens;
    the generator itself touches nothing but the bus.
    """
    account = _account(request)
    conn = _conn(request)
    try:
        conversation = MessagingService(conn).get_conversation(account, conversation_id)
    except NotFoundError as exc:
        raise PermissionDenied(
            "not a member of this conversation",
            payload={"conversation_id": conversation_id},
        ) from exc
    finally:
        close(conn)
    return StreamingResponse(
        conversation_event_stream(request, conversation.conversation_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


async def conversation_event_stream(request: Request, conversation_id: str):
    """Yield SSE frames for one conversation until the client goes away.

    Split out from the route so it can be driven directly in tests: an ASGI
    test client cannot stream an infinite response to completion. The comment
    frame keeps proxies from closing an idle stream.
    """
    queue = subscribe(conversation_id)
    try:
        while True:
            if await request.is_disconnected():
                break
            try:
                frame = await asyncio.wait_for(queue.get(), timeout=_HEARTBEAT_SECONDS)
            except asyncio.TimeoutError:
                yield ": keep-alive\n\n"
                continue
            yield encode(frame["event"], frame["data"])
    finally:
        unsubscribe(conversation_id, queue)


async def _payload(request: Request) -> dict[str, Any]:
    """The request body as a mapping, from JSON or an HTMX urlencoded form.

    Form fields that repeat (a checkbox list of member ids) collapse into a
    list instead of silently keeping the last value.
    """
    content_type = request.headers.get("content-type", "")
    if content_type.startswith("application/json"):
        body = await request.json()
        return body if isinstance(body, dict) else {}
    form = await request.form()
    packed: dict[str, Any] = {}
    for key, value in form.multi_items():
        if key in packed and isinstance(packed[key], list):
            packed[key].append(value)
        elif key in packed:
            packed[key] = [packed[key], value]
        else:
            packed[key] = value
    return packed


def _conversation_titles(
    conn,
    service: MessagingService,
    repo: AccountRepository,
    conversations: list[Any],
    account: Account,
) -> dict[str, str]:
    """A display label per direct conversation, so a list never shows a blank
    title where a direct chat has no stored name."""
    member_ids = MessagingRepository(conn)
    titles: dict[str, str] = {}
    for conversation in conversations:
        if conversation.kind == "direct":
            other_ids = [
                mid
                for mid in member_ids.member_ids(conversation.conversation_id)
                if mid != account.account_id
            ]
            names = []
            for mid in other_ids:
                peer = repo.get_account_by_id(mid)
                if peer is not None:
                    names.append(peer.display_name or peer.username)
            titles[conversation.conversation_id] = ", ".join(names) or "Direct chat"
        else:
            titles[conversation.conversation_id] = conversation.title or "Group chat"
    return titles


def _sender_names(conn, messages: list[Any]) -> dict[str, str]:
    """Account display names for the senders already loaded in a thread."""
    repo = AccountRepository(conn)
    senders: dict[str, str] = {}
    for message in messages:
        account_id = message.sender_account_id
        if account_id not in senders:
            account = repo.get_account_by_id(account_id)
            senders[account_id] = (
                account.display_name or account.username if account is not None else account_id
            )
    return senders


def _account(request: Request) -> Account:
    return request.state.account


def _conn(request: Request):
    return connect(db_path=request.app.state.settings.db_path)
