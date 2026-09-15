"""The low-code surface: the sections API and the pack administration routes.

Reads are open to any authenticated account within its own permissions.
Writes are owner-only (packs.manage) and always carry the CSRF check. The
loader validates a manifest before anything is registered, so an invalid
manifest is a typed 400, never a partial registration.
"""
from __future__ import annotations

import sqlite3
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from helix_codex_app import db
from helix_codex_app.integration import packs as pack_seam
from helix_codex_app.modules.lowcode import pack_loader, section_registry
from helix_codex_app.security.accounts import Account
from helix_codex_app.security.guard import current_account, require_csrf, require_permission
from helix_codex_app.security.permissions import permissions_for

lowcode_router = APIRouter(
    prefix="/app",
    dependencies=[Depends(current_account)],
)


class SectionRegisterRequest(BaseModel):
    """The pack whose manifest supplies the sections to register."""

    pack: str = Field(..., min_length=1)


@lowcode_router.get("/api/sections", response_model=None)
def api_sections(request: Request) -> JSONResponse:
    """The sections the caller may see, filtered by their own permissions."""
    account = request.state.account
    conn = _conn(request)
    try:
        sections = section_registry.sections_for_permissions(conn, permissions_for(account, conn))
    finally:
        db.close(conn)
    return JSONResponse({"sections": sections})


@lowcode_router.get("/api/packs", response_model=None)
def api_packs(request: Request) -> JSONResponse:
    """The persisted pack registrations, newest first."""
    conn = _conn(request)
    try:
        packs = pack_loader.registered_packs(conn)
    finally:
        db.close(conn)
    return JSONResponse({"packs": packs})


@lowcode_router.post(
    "/admin/sections",
    response_model=None,
    dependencies=[Depends(require_csrf), Depends(require_permission("packs.manage"))],
)
def admin_sections(request: Request, payload: SectionRegisterRequest) -> JSONResponse:
    """Register one pack's manifest (and its sections) for the app shell."""
    account = request.state.account
    result = _register(request, payload.pack, account)
    return JSONResponse(result, status_code=201)


@lowcode_router.post(
    "/admin/packs/reload",
    response_model=None,
    dependencies=[Depends(require_csrf), Depends(require_permission("packs.manage"))],
)
def admin_packs_reload(request: Request) -> JSONResponse:
    """Discover every manifest-bearing pack and register it fresh.

    A pack without a manifest is a legacy pack, not a broken one: it is
    reported as skipped so the answer is honest about what was not loaded.
    """
    account = request.state.account
    conn = _conn(request)
    try:
        registered: list[str] = []
        section_count = 0
        for pack_name in pack_seam.manifest_packs():
            result = _register(request, pack_name, account, conn=conn)
            registered.append(result["pack"])
            section_count += len(result["sections"])
    finally:
        db.close(conn)
    return JSONResponse(
        {
            "registered": registered,
            "section_count": section_count,
            "skipped": pack_seam.packs_without_manifest(),
        },
        status_code=201,
    )


def _register(
    request: Request,
    pack_name: str,
    account: Account,
    *,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    manifest_path = pack_seam.pack_manifest_path(pack_name)
    pack = pack_loader.load_pack(manifest_path)
    owned = conn if conn is not None else _conn(request)
    try:
        return pack_loader.register_pack(
            owned,
            pack,
            manifest_path=str(manifest_path),
            account=account,
        )
    finally:
        if conn is None:
            db.close(owned)


def _conn(request: Request) -> sqlite3.Connection:
    return db.connect(db_path=request.app.state.settings.db_path)
