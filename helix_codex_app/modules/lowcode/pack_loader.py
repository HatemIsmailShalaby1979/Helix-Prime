"""Low-code capability pack loader with the five enforced invariants.

A pack ships a capability.yaml manifest next to its Python. Loading it reads
the manifest only — none of the pack's code executes — so the file cannot be
both the contract and the backdoor. The manifest is parsed into the
CapabilityPack Protocol and validated against the five invariants before
anything is registered:

1. A pack role cannot widen the matching core role's max_financial_amount.
2. A pack cannot own a capability the core owns or another registered pack
   owns (a section's required_capability is a dependency, not ownership).
3. production_readiness below ESTABLISHED refuses a live data_mode.
4. A manifest must be semver, and min_core_version above the running core is
   refused.
5. A pack role cannot be the approver of its own action (separation of
   duties at the workflow level).

Each invariant raises a typed PackValidationError carrying an HTTP status of
400, so an invalid manifest is a client error, never a crash. validate_pack
reports the same violations as a list of messages for callers that want a
catalog of problems instead of a first-failure raise.
"""
from __future__ import annotations

import pathlib
import sqlite3
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol, runtime_checkable

import yaml

from contracts.vocabulary import PACK_DATA_MODES
from helix_codex_app import db
from helix_codex_app.errors import AppError
from helix_codex_app.integration import packs as pack_seam
from helix_codex_app.security.accounts import Account
from helix_codex_app.security.permissions import PERMISSIONS

CORE_VERSION = "0.9.0"

_ESTABLISHED = "ESTABLISHED"
_ALLOWED_PRODUCTION_READINESS = frozenset({"ESTABLISHED", "NOT_ESTABLISHED"})
_ALLOWED_DATA_MODES = PACK_DATA_MODES


class PackValidationError(AppError):
    """A capability manifest violates a loader invariant."""

    code = "pack_validation_error"
    status_code = 400


class ManifestStructureError(PackValidationError):
    """The manifest is present but does not parse into a valid contract."""

    code = "pack_manifest_structure"


class RoleLimitExceedsCoreError(PackValidationError):
    """A pack role's financial limit would widen the core role's."""

    code = "pack_role_exceeds_core_limit"


class CapabilityAlreadyOwnedError(PackValidationError):
    """A pack claims a capability the core or another pack already owns."""

    code = "pack_capability_already_owned"


class LiveDataBelowEstablishedError(PackValidationError):
    """Live data is claimed before production_readiness is ESTABLISHED."""

    code = "pack_live_data_below_established"


class CoreVersionTooOldError(PackValidationError):
    """The manifest requires a newer core than the running runtime."""

    code = "pack_core_version_too_old"


class SelfReviewError(PackValidationError):
    """A workflow's actor would be its own approver."""

    code = "pack_self_review_denied"


@dataclass(frozen=True)
class SectionDecl:
    """One shell section a manifest declares."""

    key: str
    label: str
    route: str
    required_capability: str | None = None


@dataclass(frozen=True)
class RoleDecl:
    """One pack role a manifest declares."""

    id: str
    owned_capabilities: tuple[str, ...] = ()
    approval_limits: dict[str, Any] | None = None


@dataclass(frozen=True)
class WorkflowDecl:
    """One workflow a manifest declares."""

    id: str
    actor_role: str | None = None
    requires_approval_from: str | None = None


@dataclass(frozen=True)
class CapabilityManifest:
    """A parsed capability.yaml, structurally validated."""

    schema_version: str
    id: str
    name: str
    version: str
    domain: str
    min_core_version: str
    production_readiness: str
    ontology: tuple[str, ...] = ()
    sections: tuple[SectionDecl, ...] = ()
    roles: tuple[RoleDecl, ...] = ()
    workflows: tuple[WorkflowDecl, ...] = ()
    read_only_start: bool = False
    synthetic_data_only: bool = False
    policies: tuple[dict[str, Any], ...] = ()
    connector_contracts: tuple[dict[str, Any], ...] = ()
    data_classifications: tuple[str, ...] = ()
    metrics: tuple[str, ...] = ()
    failure_modes: tuple[str, ...] = ()
    data_mode: str | None = None


@runtime_checkable
class CapabilityPack(Protocol):
    """The shape every loaded pack presents to the app.

    The manifest carries the contract; the methods mirror the blueprint's
    pack interface. A manifest-only pack answers every method from its
    declared file without importing the pack's Python.
    """

    manifest: CapabilityManifest

    def ontology(self) -> dict[str, type]:
        ...

    def roles(self) -> list[dict[str, Any]]:
        ...

    def workflows(self) -> list[dict[str, Any]]:
        ...

    def metrics(self) -> dict[str, Callable[..., Any]]:
        ...

    def runtime(self, memory: Any, *, phase: Any) -> Any:
        ...


class DeclaredEntity:
    """Marker type for an ontology entity a manifest declares but does not ship."""


def _declared_metric(name: str) -> Callable[..., Any]:
    def unavailable(*args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError(
            f"capability metric {name!r} is declared in the manifest but ships no "
            "implementation; a manifest cannot carry code"
        )

    return unavailable


class _LoadedPack:
    """A manifest-only pack: every Protocol method answers from its declared file."""

    def __init__(self, manifest: CapabilityManifest) -> None:
        self.manifest = manifest

    def ontology(self) -> dict[str, type]:
        return {name: DeclaredEntity for name in self.manifest.ontology}

    def roles(self) -> list[dict[str, Any]]:
        return [
            {
                "id": role.id,
                "owned_capabilities": list(role.owned_capabilities),
                "approval_limits": role.approval_limits,
            }
            for role in self.manifest.roles
        ]

    def workflows(self) -> list[dict[str, Any]]:
        return [
            {
                "id": workflow.id,
                "actor_role": workflow.actor_role,
                "requires_approval_from": workflow.requires_approval_from,
            }
            for workflow in self.manifest.workflows
        ]

    def metrics(self) -> dict[str, Callable[..., Any]]:
        return {name: _declared_metric(name) for name in self.manifest.metrics}

    def runtime(self, memory: Any, *, phase: Any) -> Any:
        raise NotImplementedError(
            f"pack {self.manifest.id!r} is manifest-only; its declared runtime is "
            "not executable and cannot be invoked"
        )


def _parse_version(text: str) -> tuple[int, int, int]:
    parts = text.strip().split(".")
    if len(parts) != 3 or not all(part.isdigit() for part in parts):
        raise ManifestStructureError(f"version {text!r} is not semantic MAJOR.MINOR.PATCH")
    return tuple(int(part) for part in parts)


def _require_type(value: Any, kind: type, path: str) -> None:
    if not isinstance(value, kind):
        raise ManifestStructureError(
            f"{path}: expected {kind.__name__}, got {type(value).__name__}"
        )


def _parse_section(value: Any, index: int) -> SectionDecl:
    path = f"sections[{index}]"
    _require_type(value, dict, path)
    for required in ("key", "label", "route"):
        if required not in value:
            raise ManifestStructureError(f"{path}: missing required key {required!r}")
    capability = value.get("required_capability")
    if capability is not None and not isinstance(capability, str):
        raise ManifestStructureError(f"{path}.required_capability: expected string or null")
    return SectionDecl(
        key=str(value["key"]),
        label=str(value["label"]),
        route=str(value["route"]),
        required_capability=capability,
    )


def _parse_role(value: Any, index: int) -> RoleDecl:
    path = f"roles[{index}]"
    _require_type(value, dict, path)
    if "id" not in value:
        raise ManifestStructureError(f"{path}: missing required key 'id'")
    owned = value.get("owned_capabilities", [])
    if not isinstance(owned, list) or not all(isinstance(item, str) for item in owned):
        raise ManifestStructureError(f"{path}.owned_capabilities: expected list of strings")
    limits = value.get("approval_limits")
    if limits is not None and not isinstance(limits, dict):
        raise ManifestStructureError(f"{path}.approval_limits: expected object or null")
    financial = (limits or {}).get("max_financial_amount")
    if financial is not None and not isinstance(financial, int):
        raise ManifestStructureError(
            f"{path}.approval_limits.max_financial_amount: expected integer or null"
        )
    return RoleDecl(
        id=str(value["id"]),
        owned_capabilities=tuple(owned),
        approval_limits=limits,
    )


def _parse_workflow(value: Any, index: int) -> WorkflowDecl:
    path = f"workflows[{index}]"
    _require_type(value, dict, path)
    if "id" not in value:
        raise ManifestStructureError(f"{path}: missing required key 'id'")
    actor = value.get("actor_role")
    approver = value.get("requires_approval_from")
    for label, entry in (("actor_role", actor), ("requires_approval_from", approver)):
        if entry is not None and not isinstance(entry, str):
            raise ManifestStructureError(f"{path}.{label}: expected string or null")
    return WorkflowDecl(id=str(value["id"]), actor_role=actor, requires_approval_from=approver)


def _duplicates(items: list[str], path: str) -> None:
    seen: set[str] = set()
    for item in items:
        if item in seen:
            raise ManifestStructureError(f"{path}: duplicate {item!r}")
        seen.add(item)


def _parse_manifest(data: dict[str, Any]) -> CapabilityManifest:
    required = (
        "schema_version",
        "id",
        "name",
        "version",
        "domain",
        "min_core_version",
        "production_readiness",
        "ontology",
        "sections",
        "roles",
        "workflows",
    )
    missing = [key for key in required if key not in data]
    if missing:
        raise ManifestStructureError(f"capability.yaml missing keys: {', '.join(missing)}")

    _parse_version(data["version"])
    _parse_version(data["min_core_version"])
    production_readiness = str(data["production_readiness"])
    if production_readiness not in _ALLOWED_PRODUCTION_READINESS:
        raise ManifestStructureError(
            "production_readiness must be one of "
            f"{sorted(_ALLOWED_PRODUCTION_READINESS)}, got {production_readiness!r}"
        )

    ontology = data["ontology"]
    if not isinstance(ontology, list) or not all(isinstance(item, str) for item in ontology):
        raise ManifestStructureError("ontology: expected list of strings")
    _duplicates(list(ontology), "ontology")

    sections = [_parse_section(item, index) for index, item in enumerate(data["sections"])]
    _duplicates([section.key for section in sections], "sections")
    roles = [_parse_role(item, index) for index, item in enumerate(data["roles"])]
    _duplicates([role.id for role in roles], "roles")
    workflows = [_parse_workflow(item, index) for index, item in enumerate(data["workflows"])]
    _duplicates([workflow.id for workflow in workflows], "workflows")

    for key, kind in (
        ("policies", dict),
        ("connector_contracts", dict),
    ):
        entries = data.get(key, [])
        if not isinstance(entries, list) or not all(isinstance(item, kind) for item in entries):
            raise ManifestStructureError(f"{key}: expected list of objects")

    for key in ("data_classifications", "metrics", "failure_modes"):
        entries = data.get(key, [])
        if not isinstance(entries, list) or not all(isinstance(item, str) for item in entries):
            raise ManifestStructureError(f"{key}: expected list of strings")

    for key in ("read_only_start", "synthetic_data_only"):
        if not isinstance(data.get(key, False), bool):
            raise ManifestStructureError(f"{key}: expected boolean")

    data_mode = data.get("data_mode")
    if data_mode is not None:
        if not isinstance(data_mode, str) or data_mode not in _ALLOWED_DATA_MODES:
            raise ManifestStructureError(
                f"data_mode must be one of {sorted(_ALLOWED_DATA_MODES)}, got {data_mode!r}"
            )

    return CapabilityManifest(
        schema_version=str(data["schema_version"]),
        id=str(data["id"]),
        name=str(data["name"]),
        version=str(data["version"]),
        domain=str(data["domain"]),
        min_core_version=str(data["min_core_version"]),
        production_readiness=production_readiness,
        ontology=tuple(ontology),
        sections=tuple(sections),
        roles=tuple(roles),
        workflows=tuple(workflows),
        read_only_start=bool(data.get("read_only_start", False)),
        synthetic_data_only=bool(data.get("synthetic_data_only", False)),
        policies=tuple(data.get("policies", [])),
        connector_contracts=tuple(data.get("connector_contracts", [])),
        data_classifications=tuple(data.get("data_classifications", [])),
        metrics=tuple(data.get("metrics", [])),
        failure_modes=tuple(data.get("failure_modes", [])),
        data_mode=data_mode,
    )


def _owned_capabilities(pack: CapabilityPack) -> frozenset[str]:
    return frozenset(
        capability for role in pack.manifest.roles for capability in role.owned_capabilities
    )


_REGISTERED_OWNED: dict[str, frozenset[str]] = {}


def _check_role_limits(pack: CapabilityPack) -> None:
    for role in pack.manifest.roles:
        limits = role.approval_limits or {}
        declared = limits.get("max_financial_amount")
        if declared is None:
            continue
        core_limit = pack_seam.core_role_financial_limit(role.id)
        if core_limit is None:
            continue
        if declared > core_limit:
            raise RoleLimitExceedsCoreError(
                f"pack role {role.id!r} declares max_financial_amount {declared}, "
                f"wider than the core role's {core_limit}"
            )


def _check_owned_capabilities(pack: CapabilityPack) -> None:
    owned = _owned_capabilities(pack)
    if not owned:
        return
    for capability in sorted(owned):
        if capability in PERMISSIONS:
            raise CapabilityAlreadyOwnedError(
                f"capability {capability!r} is owned by the core; a pack cannot own it"
            )
    for owner, capabilities in _REGISTERED_OWNED.items():
        clash = sorted(owned & capabilities)
        if clash:
            raise CapabilityAlreadyOwnedError(
                f"capability {clash[0]!r} is already owned by pack {owner!r}"
            )


def _check_data_mode(pack: CapabilityPack) -> None:
    if pack.manifest.production_readiness != _ESTABLISHED and pack.manifest.data_mode == "live":
        raise LiveDataBelowEstablishedError(
            f"pack {pack.manifest.id!r} claims live data before production_readiness "
            "is ESTABLISHED"
        )


def _check_core_version(pack: CapabilityPack) -> None:
    if _parse_version(pack.manifest.min_core_version) > _parse_version(CORE_VERSION):
        raise CoreVersionTooOldError(
            f"pack {pack.manifest.id!r} requires core {pack.manifest.min_core_version}, "
            f"but the runtime is {CORE_VERSION}"
        )


def _check_separation_of_duties(pack: CapabilityPack) -> None:
    for workflow in pack.manifest.workflows:
        if workflow.actor_role and workflow.requires_approval_from == workflow.actor_role:
            raise SelfReviewError(
                f"workflow {workflow.id!r}: role {workflow.actor_role!r} would "
                "review its own action"
            )


def _checks() -> tuple[Callable[[CapabilityPack], None], ...]:
    return (
        _check_role_limits,
        _check_owned_capabilities,
        _check_data_mode,
        _check_core_version,
        _check_separation_of_duties,
    )


def _raise_if_invalid(pack: CapabilityPack) -> None:
    for check in _checks():
        check(pack)


def validate_pack(pack: CapabilityPack) -> list[str]:
    """Every invariant violation as a human message, without raising.

    Each check runs independently, so a manifest with several violations is
    reported in full rather than as its first failure.
    """
    violations: list[str] = []
    for check in _checks():
        try:
            check(pack)
        except PackValidationError as exc:
            violations.append(str(exc))
    return violations


def load_pack(path: pathlib.Path | str) -> CapabilityPack:
    """Parse and validate one manifest file, raising a typed error on any failure."""
    manifest_path = pathlib.Path(path)
    if not manifest_path.is_file():
        raise ManifestStructureError(f"no capability manifest at {manifest_path}")
    raw = manifest_path.read_text(encoding="utf-8")
    try:
        data = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise ManifestStructureError(f"malformed YAML in {manifest_path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ManifestStructureError(f"{manifest_path}: expected a mapping at the top level")
    manifest = _parse_manifest(data)
    pack = _LoadedPack(manifest)
    _raise_if_invalid(pack)
    return pack


def registered_packs(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """The persisted pack registrations, newest first."""
    rows = conn.execute(
        """
        SELECT pack_id, name, version, domain, production_readiness,
               min_core_version, manifest_path, enabled, registered_at
        FROM capability_packs
        ORDER BY registered_at DESC
        """
    ).fetchall()
    return [dict(row) for row in rows]


def _record_pack_node(
    conn: sqlite3.Connection,
    pack: CapabilityPack,
    *,
    account: Account | None,
) -> str:
    envelope = _envelope(pack, "pack", account)
    return db.record_node(
        conn,
        tenant_id=envelope["tenant_id"],
        correlation_id=envelope["correlation_id"],
        classification="internal",
        nature="system_event",
        created_by=envelope["created_by"],
        provenance_source="helix_codex_app.lowcode",
        provenance_data_mode="app_runtime",
        kind="capability_pack",
        client_id=envelope["client_id"],
        domain_id=envelope["domain_id"],
        body={
            "pack_id": pack.manifest.id,
            "name": pack.manifest.name,
            "version": pack.manifest.version,
            "domain": pack.manifest.domain,
            "production_readiness": pack.manifest.production_readiness,
            "min_core_version": pack.manifest.min_core_version,
            "read_only_start": pack.manifest.read_only_start,
            "synthetic_data_only": pack.manifest.synthetic_data_only,
            "sections": [section.key for section in pack.manifest.sections],
            "roles": [role.id for role in pack.manifest.roles],
            "workflows": [workflow.id for workflow in pack.manifest.workflows],
        },
    )


def _envelope(pack: CapabilityPack, kind: str, account: Account | None) -> dict[str, str | None]:
    tenant_id = account.tenant_id if account else "platform"
    client_id = account.client_id if account else None
    domain_id = account.domain_id if account else None
    return {
        "tenant_id": tenant_id,
        "client_id": client_id,
        "domain_id": domain_id,
        "created_by": account.account_id if account else "capability_loader",
        "correlation_id": f"{kind}-{pack.manifest.id}-{uuid.uuid4().hex}",
    }


def register_pack(
    conn: sqlite3.Connection,
    pack: CapabilityPack,
    *,
    manifest_path: str | None = None,
    account: Account | None = None,
) -> dict[str, Any]:
    """Validate, then persist the pack and its sections.

    Every write goes through the governed envelope: one capability_pack node
    and one section node per declared section, committed with the row upserts.
    A pack that fails any invariant is never registered and raises the typed
    validation error.
    """
    # Imported here rather than at module scope: section_registry imports
    # SectionDecl from this module, so a module-level import would close a cycle
    # and make `import pack_loader` fail whenever pack_loader was imported first.
    from helix_codex_app.modules.lowcode import section_registry

    _raise_if_invalid(pack)
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """
        INSERT INTO capability_packs (
            pack_id, name, version, domain, production_readiness, min_core_version,
            manifest_path, enabled, registered_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?)
        ON CONFLICT(pack_id) DO UPDATE SET
            name = excluded.name,
            version = excluded.version,
            domain = excluded.domain,
            production_readiness = excluded.production_readiness,
            min_core_version = excluded.min_core_version,
            manifest_path = excluded.manifest_path,
            enabled = 1,
            registered_at = excluded.registered_at
        """,
        (
            pack.manifest.id,
            pack.manifest.name,
            pack.manifest.version,
            pack.manifest.domain,
            pack.manifest.production_readiness,
            pack.manifest.min_core_version,
            manifest_path,
            now,
        ),
    )
    _record_pack_node(conn, pack, account=account)
    _REGISTERED_OWNED[pack.manifest.id] = _owned_capabilities(pack)
    registered_sections = section_registry.register_sections(
        conn,
        pack.manifest.id,
        pack.manifest.sections,
        account=account,
    )
    conn.commit()
    return {
        "pack": pack.manifest.id,
        "name": pack.manifest.name,
        "version": pack.manifest.version,
        "sections": [section["key"] for section in registered_sections],
    }
