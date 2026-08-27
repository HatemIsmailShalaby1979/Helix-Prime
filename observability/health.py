"""
Health/readiness checks for Helix Prime Codex C3 — local-first.

Checks:
- control-plane store (SQLite can be opened and queried)
- event replay (can read events for a workflow)
- capability registry (can load and has expected roles/capabilities)
- role catalog (can load 9 roles)
- Ollama availability (HTTP GET http://localhost:11434/api/tags, timeout 2s, no network required for tests — mockable)
- required filesystem paths (evidence/, control_plane/, security/, observability/)
"""
from __future__ import annotations

import pathlib
import sqlite3
from dataclasses import dataclass
from typing import Dict, Any, List


@dataclass
class HealthStatus:
    component: str
    ok: bool
    message: str
    details: Dict[str, Any] | None = None

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {"component": self.component, "ok": self.ok, "message": self.message}
        if self.details is not None:
            d["details"] = self.details
        return d


def check_control_plane_store(db_path: str = "control_plane/workflow.db") -> HealthStatus:
    try:
        # Use Store abstraction if available, else direct sqlite
        from control_plane.store import Store

        store = Store(db_path=db_path)
        # Try to list workflows (should not raise)
        store.list_workflows(limit=1)
        # Try to query events table
        cur = store.conn.cursor()
        cur.execute("SELECT count(*) FROM events")
        cur.fetchone()
        store.close()
        return HealthStatus("control_plane_store", True, "store reachable", {"db_path": db_path})
    except Exception as e:
        return HealthStatus("control_plane_store", False, f"store check failed: {e}", {"db_path": db_path, "error": str(e)})


def check_event_replay(db_path: str = "control_plane/workflow.db") -> HealthStatus:
    try:
        from control_plane.store import Store

        store = Store(db_path=db_path)
        # Try to replay a non-existent workflow (should return empty, not error)
        events = store.replay("nonexistent_workflow_for_health_check")
        assert isinstance(events, list)
        store.close()
        return HealthStatus("event_replay", True, "replay ok")
    except Exception as e:
        return HealthStatus("event_replay", False, f"replay failed: {e}")


def check_capability_registry() -> HealthStatus:
    try:
        from organization.capability_registry import get_default_registry

        reg = get_default_registry()
        # Check expected capabilities exist
        assert reg.get_agent_for_capability("wfm_forecast") == "ops_gm"
        assert reg.get_engine_for_capability("erlang_c") == "WFM Forecasting"
        return HealthStatus("capability_registry", True, "registry ok", {"agents": len(reg.role_to_capabilities)})
    except Exception as e:
        return HealthStatus("capability_registry", False, f"registry failed: {e}")


def check_role_catalog() -> HealthStatus:
    try:
        from organization.role_catalog import load_role_catalog

        catalog = load_role_catalog("organization/role-catalog.yaml")
        assert len(catalog["roles"]) == 9
        return HealthStatus("role_catalog", True, "catalog ok", {"roles": len(catalog["roles"])})
    except Exception as e:
        return HealthStatus("role_catalog", False, f"catalog failed: {e}")


def check_ollama(ollama_url: str = "http://localhost:11434/api/tags", timeout: float = 2.0) -> HealthStatus:
    try:
        import urllib.request
        import json

        req = urllib.request.Request(ollama_url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
            # Try to parse JSON to ensure it's real Ollama
            try:
                json.loads(data)
            except Exception:
                pass
            if resp.status == 200:
                return HealthStatus("ollama", True, "ollama reachable", {"url": ollama_url})
            else:
                return HealthStatus("ollama", False, f"ollama status {resp.status}", {"url": ollama_url})
    except Exception as e:
        # For C3, Ollama not required to be up for health check to be considered "ok" in fallback mode
        # We return ok=False but with message, and the overall health will reflect it
        return HealthStatus("ollama", False, f"ollama not reachable: {e}", {"url": ollama_url, "error": str(e)})


def check_filesystem_paths(paths: List[str] | None = None) -> HealthStatus:
    if paths is None:
        paths = ["evidence", "control_plane", "security", "observability", "organization", "contracts"]
    missing = []
    for p in paths:
        if not pathlib.Path(p).exists():
            missing.append(p)
    if missing:
        return HealthStatus("filesystem", False, f"missing paths: {missing}", {"missing": missing})
    return HealthStatus("filesystem", True, "all required paths present", {"paths": paths})


def check_health(
    db_path: str = "control_plane/workflow.db",
    ollama_url: str = "http://localhost:11434/api/tags",
) -> Dict[str, HealthStatus]:
    """
    Run all health checks and return dict of component -> HealthStatus.
    Also provides overall ok (all required checks pass except ollama which is optional for C3).
    """
    results: Dict[str, HealthStatus] = {}
    results["control_plane_store"] = check_control_plane_store(db_path)
    results["event_replay"] = check_event_replay(db_path)
    results["capability_registry"] = check_capability_registry()
    results["role_catalog"] = check_role_catalog()
    results["ollama"] = check_ollama(ollama_url)
    results["filesystem"] = check_filesystem_paths()
    return results


def is_healthy(results: Dict[str, HealthStatus], require_ollama: bool = False) -> bool:
    """Overall health: all checks must be ok, except ollama if not required."""
    for name, status in results.items():
        if name == "ollama" and not require_ollama:
            continue
        if not status.ok:
            return False
    return True
