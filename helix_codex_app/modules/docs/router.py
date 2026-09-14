"""The documents surface: the list, the block editor, and the JSON API.

GET routes render the list and the editor screens; the mutating routes
write one governed node per action through DocsService. The editor is a
plain contenteditable list: reading works without a single line of
JavaScript, and only saving needs HTMX. Mutating routes accept a JSON body
or an HTMX urlencoded form through the same _payload() helper used by the
messaging module.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse

from helix_codex_app.db import close, connect
from helix_codex_app.errors import NotFoundError
from helix_codex_app.modules.docs.service import DocsService
from helix_codex_app.security.accounts import Account
from helix_codex_app.security.guard import current_account, require_csrf, require_permission
from helix_codex_app.templating import render

docs_router = APIRouter(
    prefix="/app",
    dependencies=[Depends(current_account), Depends(require_permission("docs.read"))],
)


@docs_router.get("/docs", response_model=None)
def docs_list_screen(request: Request) -> HTMLResponse:
    """The document list with a create button and search."""
    account = _account(request)
    q = request.query_params.get("q") or ""
    conn = _conn(request)
    try:
        documents = DocsService(conn).list_documents(account, {"q": q})
    finally:
        close(conn)
    context = {"account": account, "documents": documents, "q": q}
    if request.headers.get("hx-request") == "true":
        return render(request, "partials/doc_list.html", context)
    return render(
        request,
        "docs.html",
        {"active_nav": "docs", **context},
    )


@docs_router.get("/docs/{document_id}", response_model=None)
def doc_editor_screen(request: Request, document_id: str) -> HTMLResponse:
    """One document with its blocks, editable in place."""
    account = _account(request)
    conn = _conn(request)
    try:
        service = DocsService(conn)
        document = service.get_document(account, document_id)
        blocks = service.list_blocks(account, document_id)
    finally:
        close(conn)
    return render(
        request,
        "docs/editor.html",
        {
            "active_nav": "docs",
            "account": account,
            "document": document,
            "blocks": blocks,
        },
    )


@docs_router.post(
    "/api/documents",
    response_model=None,
    dependencies=[Depends(require_csrf), Depends(require_permission("docs.write"))],
)
async def create_document_route(request: Request) -> JSONResponse | HTMLResponse:
    """Create a document and record one governed node."""
    account = _account(request)
    try:
        raw = await _payload(request)
        title = str(raw.get("title", "")).strip()
        if not title:
            return JSONResponse({"error": "a document needs a title"}, status_code=400)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    conn = _conn(request)
    hx_fragment = None
    try:
        service = DocsService(conn)
        document = service.create_document(account, title)
        if request.headers.get("hx-request") == "true":
            documents = service.list_documents(account, {"q": ""})
            hx_fragment = render(
                request,
                "partials/doc_list.html",
                {"account": account, "documents": documents, "q": ""},
            )
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    finally:
        close(conn)
    if hx_fragment is not None:
        return hx_fragment
    return JSONResponse(document.to_dict(), status_code=201)


@docs_router.get("/api/documents/{document_id}", response_model=None)
def get_document_route(request: Request, document_id: str) -> JSONResponse:
    """One document with its blocks, tenant scoped."""
    account = _account(request)
    conn = _conn(request)
    try:
        service = DocsService(conn)
        document = service.get_document(account, document_id)
        blocks = service.list_blocks(account, document_id)
    except NotFoundError as exc:
        return JSONResponse({"error": str(exc)}, status_code=404)
    finally:
        close(conn)
    return JSONResponse(
        {"document": document.to_dict(), "blocks": [block.to_dict() for block in blocks]}
    )


@docs_router.put(
    "/api/documents/{document_id}/blocks/{block_id}",
    response_model=None,
    dependencies=[Depends(require_csrf), Depends(require_permission("docs.write"))],
)
async def update_block_route(
    request: Request,
    document_id: str,
    block_id: str,
) -> JSONResponse:
    """Overwrite one block's content. The later write wins and is recorded."""
    account = _account(request)
    try:
        raw = await _payload(request)
        content = raw.get("content")
        if content is None:
            return JSONResponse({"error": "content is required"}, status_code=400)
        content = str(content)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    conn = _conn(request)
    try:
        block = DocsService(conn).update_block(account, document_id, block_id, content)
    except NotFoundError as exc:
        return JSONResponse({"error": str(exc)}, status_code=404)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    finally:
        close(conn)
    return JSONResponse(block.to_dict())


@docs_router.post(
    "/api/documents/{document_id}/blocks",
    response_model=None,
    dependencies=[Depends(require_csrf), Depends(require_permission("docs.write"))],
)
async def insert_block_route(request: Request, document_id: str) -> JSONResponse | HTMLResponse:
    """Append one block to a document and record one governed node."""
    account = _account(request)
    try:
        raw = await _payload(request) if await _has_body(request) else {}
        content = raw.get("content")
    except ValueError:
        content = None
    if content is None:
        content = ""
    conn = _conn(request)
    hx_fragment = None
    try:
        service = DocsService(conn)
        block = service.insert_block(account, document_id, str(content))
        if request.headers.get("hx-request") == "true":
            document = service.get_document(account, document_id)
            blocks = service.list_blocks(account, document_id)
            hx_fragment = render(
                request,
                "partials/doc_editor.html",
                {"document": document, "blocks": blocks},
            )
    except NotFoundError as exc:
        return JSONResponse({"error": str(exc)}, status_code=404)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    finally:
        close(conn)
    if hx_fragment is not None:
        return hx_fragment
    return JSONResponse(block.to_dict(), status_code=201)


async def _has_body(request: Request) -> bool:
    content_type = request.headers.get("content-type", "")
    return bool(content_type) and (
        content_type.startswith("application/json")
        or content_type.startswith("application/x-www-form-urlencoded")
    )


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
