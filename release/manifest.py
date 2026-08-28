"""
Helix Prime Codex C8 — release manifest.

Builds a machine-readable manifest capturing the release identity and the
boundary for a candidate/pilot: version, git commit, build timestamp,
supported runtime, dependency lock reference, enabled/disabled capabilities,
data schema versions, known limitations, and evidence references.
"""

from __future__ import annotations

import datetime
import json
import pathlib
import subprocess
import sys
from typing import Any, Dict, List, Optional

ROOT = pathlib.Path(__file__).resolve().parent.parent

MANIFEST_SCHEMA_VERSION = "1.0"

# Capabilities that are intentionally NOT enabled in C8 (non-goals).
DISABLED_CAPABILITIES = [
    "cloud_deployment",
    "external_identity_provider",
    "cloud_observability",
    "network_sibling_transport",
    "autonomous_irreversible_actions",
]

# Known limitations / boundary (matched from the C8 ticket non-goals + residual risk).
KNOWN_LIMITATIONS = [
    "Local SQLite persistence only — no cloud redundancy or HA.",
    "Local filesystem permissions assumed; no external IdP or RBAC-backed directory.",
    "Ollama model trust is assumed (local, user-controlled); no remote model attestation.",
    "Sibling transport is local/in-process only; network sibling transport deferred.",
    "No autonomous irreversible/financial/personnel/compliance/external-communication actions.",
    "Pilot data must be limited to synthetic or explicitly consented data.",
    "Production label not claimed without every production gate passing.",
]


def _git_head() -> Optional[str]:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(ROOT), capture_output=True, text=True, timeout=3,
        )
        if out.returncode == 0:
            return out.stdout.strip()
    except Exception:
        pass
    return None


def _git_branch() -> Optional[str]:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=str(ROOT), capture_output=True, text=True, timeout=3,
        )
        if out.returncode == 0:
            return out.stdout.strip()
    except Exception:
        pass
    return None


def _read_versions(rel_path: str) -> List[str]:
    p = ROOT / rel_path
    if not p.exists():
        return []
    lines = [ln.strip() for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]
    return lines


def data_schema_versions() -> Dict[str, str]:
    """Read schema versions declared by the system components."""
    versions: Dict[str, str] = {}
    audit_p = ROOT / "security" / "audit.py"
    if audit_p.exists():
        for ln in audit_p.read_text(encoding="utf-8").splitlines():
            if ln.startswith("SCHEMA_VERSION"):
                versions["security.audit"] = ln.split("=")[1].strip().strip('"').strip("'")
    try:
        from control_plane.store import SCHEMA_VERSION as cp_schema
        versions["control_plane.store"] = cp_schema
    except Exception:
        versions.setdefault("control_plane.store", "unknown")
    return versions


def build_manifest(
    classification: str = "PENDING",
    profile: str = "production_candidate",
    release_approved: bool = False,
    include_full_path: bool = False,
) -> Dict[str, Any]:
    """Build a deterministic, machine-readable release manifest."""
    deps = _read_versions("release/requirements.lock.txt")
    manifest: Dict[str, Any] = {
        "manifest_schema_version": MANIFEST_SCHEMA_VERSION,
        "product": "Helix-Prime-Codex",
        "release_profile": profile,
        "classification": classification,
        "release_approved": bool(release_approved),
        "version": "0.9.0-c8",
        "git_commit": _git_head() or "unknown",
        "git_branch": _git_branch() or "unknown",
        "build_timestamp": datetime.datetime.now(datetime.timezone.utc)
        .isoformat()
        .replace("+00:00", "Z"),
        "python_version": sys.version.split()[0],
        "platform": sys.platform,
        "supported_python": ">=3.10",
        "dependency_lock_ref": "release/requirements.lock.txt",
        "dependency_lock_count": len(deps),
        "enabled_capabilities": [
            "control_plane", "six_engines", "nine_agents",
            "vertical_slice", "audit", "classification",
            "authorization", "sibling_transport(local)",
            "gm_expansion",
        ],
        "disabled_capabilities": DISABLED_CAPABILITIES,
        "data_schema_versions": data_schema_versions(),
        "known_limitations": KNOWN_LIMITATIONS,
        "evidence_refs": [],
    }
    if include_full_path:
        manifest["paths"] = {
            "control_plane_db": "control_plane/workflow.db",
            "audit_db": "security/audit.db",
            "observability_log": "observability/logs.jsonl",
            "release_profiles": "release/release-profiles.yaml",
            "manifest_schema": "release/manifest.schema.json",
        }
    return manifest


def write_manifest(
    manifest: Dict[str, Any],
    rel_path: str = "release/release-manifest.json",
) -> str:
    """Write the manifest to disk and return the absolute path."""
    out = ROOT / rel_path
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(manifest, f, default=str, indent=2)
    return str(out)


def load_manifest(rel_path: str = "release/release-manifest.json") -> Dict[str, Any]:
    p = ROOT / rel_path
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)
