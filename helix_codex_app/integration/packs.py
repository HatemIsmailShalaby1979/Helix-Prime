"""Capability-pack discovery.

A pack declares what it provides in its own register.py metadata. The app reads
that rather than keeping a second list, so a pack added under capabilities/ shows
up without an app change. Discovery never invents a pack: metadata that cannot be
read raises, because a silently missing pack looks the same as a pack with
nothing in it.
"""
from __future__ import annotations

import importlib
import pathlib
from typing import Any

from helix_codex_app.errors import EngineUnavailableError, NotFoundError
from organization import role_catalog

CAPABILITIES_DIR = pathlib.Path(__file__).resolve().parents[2] / "capabilities"
MANIFEST_NAME = "capability.yaml"
COCKPIT_VIEW_KEYS: tuple[str, ...] = ("owner", "coach", "parent")
COCKPIT_SECTION_CAPABILITY = "cockpit.view"


def pack_manifest_path(pack: str) -> pathlib.Path:
    """The capability.yaml a pack must ship to be loaded by the low-code loader."""
    if pack not in pack_names():
        raise NotFoundError(f"unknown capability pack {pack!r}")
    return CAPABILITIES_DIR / pack / MANIFEST_NAME


def manifest_packs() -> list[str]:
    """Discoverable packs that already ship a capability manifest."""
    return sorted(
        pack for pack in pack_names() if (CAPABILITIES_DIR / pack / MANIFEST_NAME).is_file()
    )


def packs_without_manifest() -> list[str]:
    """Discoverable packs that have not shipped a capability manifest yet."""
    return sorted(
        pack for pack in pack_names() if not (CAPABILITIES_DIR / pack / MANIFEST_NAME).is_file()
    )


def core_role_financial_limit(role_id: str) -> int | None:
    """The core role's max_financial_amount, or None when it has no cap.

    The core role catalog is the never-edited organization/role-catalog.yaml.
    The loader compares a pack role's declared limit against this value, so a
    manifest can never widen what the catalog grants.
    """
    catalog = role_catalog.load_role_catalog()
    role = (catalog.get("roles_by_id") or {}).get(role_id)
    if role is None:
        return None
    limits = role.get("approval_limits") or {}
    return limits.get("max_financial_amount")


def pack_names() -> list[str]:
    """Every subpackage of capabilities/ that ships a register.py."""
    if not CAPABILITIES_DIR.is_dir():
        raise EngineUnavailableError("the capabilities directory is missing")
    return sorted(
        entry.name
        for entry in CAPABILITIES_DIR.iterdir()
        if entry.is_dir() and (entry / "register.py").is_file()
    )


def pack_metadata(pack: str) -> dict[str, Any]:
    """One pack's declared metadata.

    The metadata function is found by name rather than hard-coded per pack, so
    a new pack does not need an entry here. A pack that declares nothing usable
    raises instead of reporting an empty capability.
    """
    if pack not in pack_names():
        raise NotFoundError(f"unknown capability pack {pack!r}")
    try:
        module = importlib.import_module(f"capabilities.{pack}.register")
    except ImportError as exc:
        raise EngineUnavailableError(
            f"capability pack {pack!r} could not be imported: {exc}"
        ) from exc
    for name in sorted(dir(module)):
        if name.startswith("get_") and name.endswith("_metadata"):
            function = getattr(module, name)
            if callable(function):
                return dict(function())
    raise EngineUnavailableError(f"capability pack {pack!r} exposes no metadata function")


def list_packs() -> list[dict[str, Any]]:
    """Every pack with the parts of its metadata the app actually uses."""
    out: list[dict[str, Any]] = []
    for pack in pack_names():
        meta = pack_metadata(pack)
        out.append(
            {
                "pack": pack,
                "name": meta.get("name", pack),
                "domain": meta.get("domain", pack),
                "version": meta.get("version"),
                "production_readiness": meta.get("production_readiness"),
                "read_only_start": bool(meta.get("read_only_start", False)),
                "synthetic_data_only": bool(meta.get("synthetic_data_only", False)),
                "ontology": list(meta.get("ontology", [])),
                "metrics": list(meta.get("metrics", [])),
                "roles": list(meta.get("roles", [])),
                "workflows": list(meta.get("workflows", [])),
            }
        )
    return out


def pack_sections(pack: str) -> list[dict[str, Any]]:
    """The shell sections a pack contributes, one per cockpit view it ships.

    Each section is gated by cockpit.view, so a pack cannot hand out access to
    itself. A pack whose production_readiness is not ESTABLISHED is marked
    simulated-only, and the badge that says so is not optional.
    """
    meta = pack_metadata(pack)
    views = CAPABILITIES_DIR / pack / "cockpit_views"
    if not views.is_dir():
        return []
    simulated_only = meta.get("production_readiness") != "ESTABLISHED"
    sections: list[dict[str, Any]] = []
    for key in COCKPIT_VIEW_KEYS:
        if not any(views.glob(f"{key}*.py")):
            continue
        sections.append(
            {
                "key": key,
                "label": key.title(),
                "route": f"/app/cockpit/{key}",
                "required_capability": COCKPIT_SECTION_CAPABILITY,
                "pack": pack,
                "simulated_only": simulated_only,
            }
        )
    return sections


def all_sections() -> list[dict[str, Any]]:
    """Every section every pack contributes, for the shell to render."""
    out: list[dict[str, Any]] = []
    for pack in pack_names():
        out.extend(pack_sections(pack))
    return out
