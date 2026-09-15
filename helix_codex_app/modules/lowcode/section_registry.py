"""Registered shell sections: register pack declarations, query by permission.

The sections table is the source the shell's nav renders from. Registering is
an upsert keyed by `{pack}:{key}`, so re-running a registration refreshes the
label, route, and position instead of stacking rows. Reading filters by the
caller's permission keys; a section whose required_capability the caller lacks
is absent, never rendered disabled, so the nav cannot leak a link to a gate.
"""
from __future__ import annotations

import sqlite3
import uuid
from typing import Any

from helix_codex_app import db
from helix_codex_app.modules.lowcode.pack_loader import SectionDecl
from helix_codex_app.security.accounts import Account


def _section_envelope(pack_id: str, account: Account | None) -> dict[str, str | None]:
    return {
        "tenant_id": account.tenant_id if account else "platform",
        "client_id": account.client_id if account else None,
        "domain_id": account.domain_id if account else None,
        "created_by": account.account_id if account else "capability_loader",
        "correlation_id": f"section-{pack_id}-{uuid.uuid4().hex}",
    }


def register_sections(
    conn: sqlite3.Connection,
    pack_id: str,
    sections: tuple[SectionDecl, ...],
    *,
    account: Account | None = None,
) -> list[dict[str, Any]]:
    """Upsert one section row per declaration and record a governed node each."""
    registered: list[dict[str, Any]] = []
    for position, section in enumerate(sections):
        section_id = f"{pack_id}:{section.key}"
        conn.execute(
            """
            INSERT INTO sections (
                section_id, domain_id, key, label, icon, route, position,
                required_capability, enabled, source_pack
            ) VALUES (?, NULL, ?, ?, NULL, ?, ?, ?, 1, ?)
            ON CONFLICT(section_id) DO UPDATE SET
                key = excluded.key,
                label = excluded.label,
                route = excluded.route,
                position = excluded.position,
                required_capability = excluded.required_capability,
                enabled = 1,
                source_pack = excluded.source_pack
            """,
            (
                section_id,
                section.key,
                section.label,
                section.route,
                position,
                section.required_capability,
                pack_id,
            ),
        )
        envelope = _section_envelope(pack_id, account)
        db.record_node(
            conn,
            tenant_id=envelope["tenant_id"],
            correlation_id=envelope["correlation_id"],
            classification="internal",
            nature="system_event",
            created_by=envelope["created_by"],
            provenance_source="helix_codex_app.lowcode",
            provenance_data_mode="app_runtime",
            kind="section",
            client_id=envelope["client_id"],
            domain_id=envelope["domain_id"],
            body={
                "pack_id": pack_id,
                "section_id": section_id,
                "key": section.key,
                "label": section.label,
                "route": section.route,
                "required_capability": section.required_capability,
                "position": position,
            },
        )
        registered.append(
            {
                "key": section.key,
                "label": section.label,
                "route": section.route,
                "required_capability": section.required_capability,
            }
        )
    conn.commit()
    return registered


def sections_for_permissions(
    conn: sqlite3.Connection,
    permission_keys: set[str] | frozenset[str],
) -> list[dict[str, Any]]:
    """The enabled sections the caller may see, in declared order.

    A section without a required_capability is visible to everyone. A section
    whose source pack is not registered as ESTABLISHED is marked
    simulated_only — the badge that says so is computed here, not in a
    template that could forget it.
    """
    rows = conn.execute(
        """
        SELECT s.section_id, s.key, s.label, s.route, s.required_capability,
               s.source_pack, p.production_readiness AS pack_production_readiness
        FROM sections s
        LEFT JOIN capability_packs p ON p.pack_id = s.source_pack
        WHERE s.enabled = 1
        ORDER BY s.position ASC, s.rowid ASC
        """
    ).fetchall()
    sections: list[dict[str, Any]] = []
    for row in rows:
        required = row["required_capability"]
        if required is not None and required not in permission_keys:
            continue
        sections.append(
            {
                "section_id": row["section_id"],
                "key": row["key"],
                "label": row["label"],
                "route": row["route"],
                "required_capability": required,
                "pack": row["source_pack"],
                "simulated_only": row["pack_production_readiness"] != "ESTABLISHED",
            }
        )
    return sections
