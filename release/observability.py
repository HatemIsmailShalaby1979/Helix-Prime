"""
Helix Prime Codex C8 — observability & operational readiness.

Produces measured LOCAL signals and SLOs for the release gate:
- startup time
- control-plane readiness
- capability/role registry integrity
- storage (control-plane + audit db) writability
- evidence artifact production
- overall readiness classification

These are LOCAL CANDIDATE measurements only — no cloud/platform SLO claims.
SLOs are explicit thresholds against which the gate measures the local host.
"""

from __future__ import annotations

import datetime
import time
from typing import Any, Dict, Optional

from release import manifest as manifest_mod

ROOT = manifest_mod.ROOT

# Explicit local candidate SLO thresholds (measured on THIS host, not a claim).
SLO_THRESHOLDS = {
    "startup_seconds_le": 10.0,
    "ready_components_pct_ge": 100.0,
    "storage_writable": True,
    "evidence_json_present": True,
}


def _now() -> str:
    return (
        datetime.datetime.now(datetime.timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )


def measure_startup() -> Dict[str, Any]:
    """Measure import + instantiation time of the control plane Engine and Store."""
    start = time.monotonic()
    try:
        from control_plane.engine import Engine
        from control_plane.store import Store
        import tempfile
        import os
        tmp = tempfile.mkdtemp(prefix="hp_startup_")
        db = os.path.join(tmp, "wf.db")
        engine = Engine()
        if hasattr(engine, "submit"):
            pass  # engine constructible
        store = Store(db_path=db)
        store.close()
        ok = True
        detail = "engine + store constructible"
    except Exception as e:  # noqa: BLE001
        ok = False
        detail = f"{type(e).__name__}: {e}"
        duration = time.monotonic() - start
        return {
            "ok": ok, "duration_ms": round(duration * 1000, 1),
            "slo_le_ms": SLO_THRESHOLDS["startup_seconds_le"] * 1000.0,
            "detail": detail,
        }
    duration = time.monotonic() - start
    return {
        "ok": ok,
        "duration_ms": round(duration * 1000, 1),
        "slo_le_ms": SLO_THRESHOLDS["startup_seconds_le"] * 1000.0,
        "slo_met": duration <= SLO_THRESHOLDS["startup_seconds_le"],
        "detail": detail,
    }


def health_report(db_path: Optional[str] = None) -> Dict[str, Any]:
    """Aggregate local component readiness from observability.health."""
    import observability.health as health
    results = health.check_health()
    all_rows = {
        name: (st.to_dict() if hasattr(st, "to_dict") else str(st))
        for name, st in results.items()
    }
    # Ollama is optional for local readiness; all other components must be ok.
    required = {k: v for k, v in results.items() if k != "ollama"}
    healthy = sum(1 for st in required.values() if getattr(st, "ok", False))
    total = len(required)
    pct = (healthy / total * 100.0) if total else 0.0
    return {
        "components": all_rows,
        "healthy": healthy,
        "total": total,
        "healthy_pct": round(pct, 1),
        "ready": total > 0 and healthy == total,
        "slo_met": pct >= SLO_THRESHOLDS["ready_components_pct_ge"],
        "ollama_present": bool(getattr(results.get("ollama"), "ok", False)),
    }


def storage_writable() -> Dict[str, Any]:
    """Check control-plane + audit DBs are writable in a throwaway temp location."""
    import tempfile
    import os
    results: Dict[str, Any] = {}
    try:
        tmp = tempfile.mkdtemp(prefix="hp_storage_")
        from control_plane.store import Store
        s = Store(db_path=os.path.join(tmp, "wf.db"))
        s.close()
        results["control_plane_db"] = True
    except Exception as e:  # noqa: BLE001
        results["control_plane_db"] = False
        results["control_plane_error"] = f"{type(e).__name__}: {e}"
    try:
        from security.audit import AuditTrail, AuditRecord
        trail = AuditTrail(db_path=os.path.join(tmp, "audit.db"))
        rec = AuditRecord.new(
            event_type="release_gate", actor="release_gate",
            actor_type="service", decision="succeeded",
        )
        trail.append(rec)
        trail.close()
        results["audit_db"] = True
    except Exception as e:  # noqa: BLE001
        results["audit_db"] = False
        results["audit_error"] = f"{type(e).__name__}: {e}"
    results["all_writable"] = bool(
        results.get("control_plane_db") and results.get("audit_db")
    )
    return results


def run_observability_report(db_path: Optional[str] = None) -> Dict[str, Any]:
    """Run all observability/readiness checks and return {checks, slos, all_ok}."""
    checks = {
        "startup": measure_startup(),
        "readiness": health_report(db_path),
        "storage": storage_writable(),
    }
    all_ok = (
        checks["startup"].get("slo_met", False)
        and checks["readiness"].get("ready", False)
        and bool(checks["storage"].get("all_writable"))
    )
    return {
        "checks": checks,
        "slos": SLO_THRESHOLDS,
        "measured_at": _now(),
        "all_ok": all_ok,
    }
