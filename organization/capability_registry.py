"""
Capability registry for Helix Prime Codex C1a.

Canonical source of truth:
- organization/capability-registry.yaml is the ONE canonical file for engine capabilities.
  Mirrors contracts/capabilities.yaml and organization/capabilities.json are GENERATED
  and MUST have identical engine_capabilities as the canonical. Drift is detected
  by tests/test_capability_registry_drift.py and by validate_mirrors() below.
  Do not maintain independent hand-edited copies.

Other canonical:
- Agent capabilities: organization/role-catalog.yaml (owned_capabilities per role)

Provides deterministic, fail-closed lookup for:
- agent capability -> owning role
- engine capability -> engine name
- role -> capabilities
- tool allow-list per role
- discover + route_task_request for TaskRequest

Preserves legacy name-based routing via compatibility; does not break existing orchestrator.
Preserves all C1a APIs: get_agent_for_capability, get_engine_for_capability, etc.
"""
from __future__ import annotations

import pathlib
from typing import Any, Dict, List, Set, Optional

try:
    import yaml  # type: ignore
except ImportError:
    yaml = None  # type: ignore

from organization.role_catalog import load_role_catalog

DEFAULT_ROLE_CATALOG = "organization/role-catalog.yaml"
DEFAULT_CAPABILITY_REGISTRY = "organization/capability-registry.yaml"


class CapabilityRegistry:
    """
    Deterministic capability registry.

    - Agent capabilities are built from role catalog (unique per capability, else ambiguous).
    - Engine capabilities are loaded from capability-registry.yaml.
    - Unknown or ambiguous lookups fail closed (ValueError).
    """

    def __init__(
        self,
        agent_capability_to_role: Dict[str, str],
        agent_capability_to_roles: Dict[str, List[str]],
        engine_capability_to_engine: Dict[str, str],
        engine_capability_to_engines: Dict[str, List[str]],
        role_to_capabilities: Dict[str, List[str]],
        role_to_tools: Dict[str, List[str]],
        ambiguous_agent_capabilities: Set[str],
        ambiguous_engine_capabilities: Set[str],
        source: str = "default",
    ):
        self.agent_capability_to_role = agent_capability_to_role
        self.agent_capability_to_roles = agent_capability_to_roles
        self.engine_capability_to_engine = engine_capability_to_engine
        self.engine_capability_to_engines = engine_capability_to_engines
        self.role_to_capabilities = role_to_capabilities
        self.role_to_tools = role_to_tools
        self.ambiguous_agent_capabilities = ambiguous_agent_capabilities
        self.ambiguous_engine_capabilities = ambiguous_engine_capabilities
        self.source = source

    # ── agent ────────────────────────────────────────────────────────────────
    def get_agent_for_capability(self, capability: str) -> str:
        cap = capability.strip()
        if not cap:
            raise ValueError("get_agent_for_capability: capability must be non-empty string")
        if cap in self.ambiguous_agent_capabilities:
            owners = self.agent_capability_to_roles.get(cap, [])
            raise ValueError(f"ambiguous capability {cap!r} owned by multiple roles {owners} — fail closed to review queue")
        if cap not in self.agent_capability_to_role:
            raise ValueError(f"unknown capability {cap!r} for agent lookup — fail closed")
        return self.agent_capability_to_role[cap]

    def get_capabilities_for_role(self, role_id: str) -> List[str]:
        if role_id not in self.role_to_capabilities:
            raise ValueError(f"role {role_id!r} not found in capability registry")
        # return copy to prevent mutation
        return list(self.role_to_capabilities[role_id])

    def is_capability_owned_by_role(self, role_id: str, capability: str) -> bool:
        if role_id not in self.role_to_capabilities:
            raise ValueError(f"role {role_id!r} not found")
        return capability in self.role_to_capabilities[role_id]

    def is_tool_allowed(self, role_id: str, tool: str) -> bool:
        if role_id not in self.role_to_tools:
            raise ValueError(f"role {role_id!r} not found for tool check")
        if not isinstance(tool, str) or not tool.strip():
            raise ValueError(f"is_tool_allowed: tool must be non-empty string, got {tool!r}")
        return tool.strip() in self.role_to_tools[role_id]

    # ── engine ───────────────────────────────────────────────────────────────
    def get_engine_for_capability(self, capability: str) -> str:
        cap = capability.strip()
        if not cap:
            raise ValueError("get_engine_for_capability: capability must be non-empty string")
        if cap in self.ambiguous_engine_capabilities:
            owners = self.engine_capability_to_engines.get(cap, [])
            raise ValueError(f"ambiguous engine capability {cap!r} owned by multiple engines {owners} — fail closed")
        if cap not in self.engine_capability_to_engine:
            raise ValueError(f"unknown capability {cap!r} for engine lookup — fail closed")
        return self.engine_capability_to_engine[cap]

    # ── unified discover + routing ───────────────────────────────────────────
    def discover(self, capability: str) -> str:
        """
        Unified discover: try agent first, then engine. Fail closed if unknown in both.
        Returns owning role or engine name. Used for unknown check in tests.
        """
        cap = capability.strip()
        if not cap:
            raise ValueError("discover: capability must be non-empty string")
        # check ambiguous first
        if cap in self.ambiguous_agent_capabilities or cap in self.ambiguous_engine_capabilities:
            raise ValueError(f"ambiguous capability {cap!r} — fail closed")
        if cap in self.agent_capability_to_role:
            return self.agent_capability_to_role[cap]
        if cap in self.engine_capability_to_engine:
            return self.engine_capability_to_engine[cap]
        raise ValueError(f"unknown capability {cap!r} — fail closed (no agent or engine owner)")

    def route_task_request(self, request: Any) -> str:
        """
        Deterministic routing for TaskRequest by capability.
        Returns owning role_id for request.capability.
        Validates that capability is owned and not ambiguous.
        """
        # Lazy import to avoid circular
        from contracts.task import TaskRequest

        if not isinstance(request, TaskRequest):
            raise ValueError(f"route_task_request: expected TaskRequest, got {type(request).__name__}")
        cap = request.capability.strip()
        # Use agent lookup (TaskRequest capability is always an agent capability)
        return self.get_agent_for_capability(cap)


def build_registry_from_catalog(
    catalog_data: Dict[str, Any],
    engine_capabilities: Optional[Dict[str, str]] = None,
) -> CapabilityRegistry:
    """
    Build registry from already-loaded catalog dict (for tests with synthetic duplicates).
    If engine_capabilities not provided, tries to load from organization/capability-registry.yaml.
    """
    roles = catalog_data.get("roles", [])
    role_to_caps: Dict[str, List[str]] = {}
    role_to_tools: Dict[str, List[str]] = {}
    cap_to_roles: Dict[str, List[str]] = {}

    for role in roles:
        rid = role.get("id", "")
        caps = list(role.get("owned_capabilities", []))
        tools = list(role.get("allowed_tools", []))
        role_to_caps[rid] = caps
        role_to_tools[rid] = tools
        for cap in caps:
            cap_to_roles.setdefault(cap, []).append(rid)

    # detect ambiguous agent caps
    ambiguous_agent: Set[str] = {cap for cap, owners in cap_to_roles.items() if len(owners) > 1}
    # deterministic mapping: only unique caps get single owner
    cap_to_role: Dict[str, str] = {cap: owners[0] for cap, owners in cap_to_roles.items() if len(owners) == 1}

    # engine capabilities: load from file if not provided
    if engine_capabilities is None:
        # try to load from YAML file
        p = pathlib.Path(DEFAULT_CAPABILITY_REGISTRY)
        if p.exists() and yaml is not None:
            try:
                data = yaml.safe_load(p.read_text(encoding="utf-8"))
                engine_capabilities = data.get("engine_capabilities", {}) if isinstance(data, dict) else {}
            except Exception:
                engine_capabilities = {}
        else:
            engine_capabilities = {}

    if engine_capabilities is None:
        engine_capabilities = {}

    # engine: capability -> engine, check ambiguous
    eng_to_cap: Dict[str, List[str]] = {}
    cap_to_engines: Dict[str, List[str]] = {}
    for cap, eng in engine_capabilities.items():
        cap_to_engines.setdefault(cap, []).append(eng)
        eng_to_cap.setdefault(eng, []).append(cap)

    ambiguous_engine: Set[str] = {cap for cap, owners in cap_to_engines.items() if len(owners) > 1}
    cap_to_engine: Dict[str, str] = {cap: owners[0] for cap, owners in cap_to_engines.items() if len(owners) == 1}

    return CapabilityRegistry(
        agent_capability_to_role=cap_to_role,
        agent_capability_to_roles=cap_to_roles,
        engine_capability_to_engine=cap_to_engine,
        engine_capability_to_engines=cap_to_engines,
        role_to_capabilities=role_to_caps,
        role_to_tools=role_to_tools,
        ambiguous_agent_capabilities=ambiguous_agent,
        ambiguous_engine_capabilities=ambiguous_engine,
        source="from_catalog",
    )


# ── default singleton ──────────────────────────────────────────────────────

_default_registry: Optional[CapabilityRegistry] = None


def _load_default_registry() -> CapabilityRegistry:
    global _default_registry
    if _default_registry is not None:
        return _default_registry
    # Load role catalog
    catalog = load_role_catalog(DEFAULT_ROLE_CATALOG)
    # Load engine capabilities from registry YAML
    engine_caps: Dict[str, str] = {}
    p = pathlib.Path(DEFAULT_CAPABILITY_REGISTRY)
    if p.exists():
        if yaml is None:
            raise ValueError("PyYAML not installed: cannot load capability-registry.yaml")
        try:
            data = yaml.safe_load(p.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                engine_caps = data.get("engine_capabilities", {}) or {}
        except yaml.YAMLError as e:
            raise ValueError(f"malformed YAML in {p}: {e}") from e
    _default_registry = build_registry_from_catalog(catalog, engine_capabilities=engine_caps)
    return _default_registry


def get_default_registry() -> CapabilityRegistry:
    return _load_default_registry()


# ── module-level helpers (used by tests) ───────────────────────────────────

def get_agent_for_capability(capability: str) -> str:
    return get_default_registry().get_agent_for_capability(capability)


def get_engine_for_capability(capability: str) -> str:
    return get_default_registry().get_engine_for_capability(capability)


def get_capabilities_for_role(role_id: str) -> List[str]:
    return get_default_registry().get_capabilities_for_role(role_id)


def is_capability_owned_by_role(role_id: str, capability: str) -> bool:
    return get_default_registry().is_capability_owned_by_role(role_id, capability)


def is_tool_allowed(role_id: str, tool: str) -> bool:
    return get_default_registry().is_tool_allowed(role_id, tool)


def discover(capability: str) -> str:
    return get_default_registry().discover(capability)


def route_task_request(request: Any) -> str:
    return get_default_registry().route_task_request(request)


def validate_mirror_drift() -> None:
    """
    Drift detection for capability registry mirrors.

    Canonical: organization/capability-registry.yaml
    Mirrors must have identical engine_capabilities:
      - contracts/capabilities.yaml
      - organization/capabilities.json

    Raises ValueError with details if drift detected. Used by
    tests/test_capability_registry_drift.py and can be called at startup.
    """
    import json

    canonical_path = pathlib.Path(DEFAULT_CAPABILITY_REGISTRY)
    if not canonical_path.exists():
        raise ValueError(f"canonical capability registry not found at {canonical_path}")
    if yaml is None:
        raise ValueError("PyYAML not installed for drift check")
    canonical_data = yaml.safe_load(canonical_path.read_text(encoding="utf-8"))
    canonical_eng = (canonical_data or {}).get("engine_capabilities", {}) if isinstance(canonical_data, dict) else {}

    # Check YAML mirror
    yaml_mirror = pathlib.Path("contracts/capabilities.yaml")
    if yaml_mirror.exists():
        try:
            y_data = yaml.safe_load(yaml_mirror.read_text(encoding="utf-8"))
            y_eng = (y_data or {}).get("engine_capabilities", {}) if isinstance(y_data, dict) else {}
        except Exception as e:
            raise ValueError(f"failed to load YAML mirror {yaml_mirror}: {e}") from e
        if y_eng != canonical_eng:
            raise ValueError(
                f"drift detected: contracts/capabilities.yaml engine_capabilities != canonical "
                f"{canonical_path} — fix by regenerating mirror from canonical"
            )

    # Check JSON mirror
    json_mirror = pathlib.Path("organization/capabilities.json")
    if json_mirror.exists():
        try:
            j_data = json.loads(json_mirror.read_text(encoding="utf-8"))
            j_eng = j_data.get("engine_capabilities", {}) if isinstance(j_data, dict) else {}
        except Exception as e:
            raise ValueError(f"failed to load JSON mirror {json_mirror}: {e}") from e
        if j_eng != canonical_eng:
            raise ValueError(
                f"drift detected: organization/capabilities.json engine_capabilities != canonical "
                f"{canonical_path}"
            )


# For tests that need to build from synthetic catalog + drift detection
__all__ = [
    "CapabilityRegistry",
    "build_registry_from_catalog",
    "get_default_registry",
    "get_agent_for_capability",
    "get_engine_for_capability",
    "get_capabilities_for_role",
    "is_capability_owned_by_role",
    "is_tool_allowed",
    "discover",
    "route_task_request",
    "validate_mirror_drift",
]
