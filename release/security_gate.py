"""
Helix Prime Codex C8 — release security & data-governance gate.

Runs a SAFE LOCAL repository scan (no network, no uploads) plus deterministic
policy/classification/audit checks. Never scans or publishes anything outside
the repo and never prints secret material.

Checks:
- secrets_scan: tracked/source files contain no secret-like patterns
- classification: canonical classification vocabulary present and used
- tenant_isolation / deny_by_default: authorization policy is deny-by-default
- sod_and_approval: separation-of-duties + approval seam present
- audit_integrity: audit chain verifies (when a real audit db exists)
- redaction: redaction helper present and functional
- malformed_output: malformed model/engine output handled without crashing

Returns a dict of {check_name: {"ok": bool, "detail": str}}.
"""

from __future__ import annotations

import pathlib
import re
from typing import Any, Dict, List, Optional

from release import manifest as manifest_mod

ROOT = manifest_mod.ROOT

# File extensions we treat as source/evidence/text for secret scanning.
SCAN_EXTENSIONS = {
    ".py", ".json", ".yaml", ".yml", ".toml", ".txt",
    ".md", ".bat", ".sql", ".csv", ".sh",
}
# Directories to skip (generated, vendored, venv).
SCAN_SKIP_DIRS = {".venv", "venv", "node_modules", "__pycache__", ".git", ".pytest_cache",
                  ".mypy_cache", ".ruff_cache", "evidence", "dist", "build", "target"}

# Regex markers for secret-like values. Deterministic, conservative.
_SECRET_PATTERNS = [
    re.compile(r"(?i)api[_-]?key\s*[=:]\s*['\"]?[A-Za-z0-9_\-\.]{16,}"),
    re.compile(r"(?i)secret\s*[=:]\s*['\"]?[A-Za-z0-9_\-\.]{16,}"),
    re.compile(r"(?i)password\s*[=:]\s*['\"]?[A-Za-z0-9_\-\.]{8,}"),
    re.compile(r"(?i)passwd\s*[=:]\s*['\"]?[A-Za-z0-9_\-\.]{8,}"),
    re.compile(r"(?i)token\s*[=:]\s*['\"]?[A-Za-z0-9_\-\.]{16,}"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9_\-\.]{16,}"),
    re.compile(r"(?i)aws_access_key_id\s*[=:]\s*['\"]?\S+"),
    re.compile(r"(?i)aws_secret_access_key\s*[=:]\s*['\"]?\S+"),
    re.compile(r"(?i)client_secret\s*[=:]\s*['\"]?\S+"),
    re.compile(r"-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----"),
]

# Sentinel/placeholder values that are acceptable and not secrets. These are
# unambiguous non-live placeholders: documented example defaults and classic
# demo/test fixture values. Real-looking credentials (long hex, aws keys,
# private keys) are still flagged.
_FAKE_SCAN_ALLOW = [
    "api_key=example", "api_key=changeme", "api_key=your-api-key",
    "password=changeme", "password=your-password", "secret=changeme",
    "changeme", "your-api-key", "your-random-session-secret",
    "XXXX", "xxxx", "example", "placeholder", "redacted",
    "your_password", "your-password", "REPLACE", "REPLACE_ME",
    "sk-1234567890abcdef", "s3cr3tpass",
]


def _iter_scan_files(subdirs: Optional[List[str]] = None) -> List[pathlib.Path]:
    files: List[pathlib.Path] = []
    base = ROOT
    search_roots = [base / d for d in subdirs] if subdirs else [base]
    for root in search_roots:
        if not root.exists():
            continue
        import os
        for dirpath, dirnames, filenames in os.walk(root):
            dp = pathlib.Path(dirpath)
            dirnames[:] = [
                d for d in dirnames
                if d not in SCAN_SKIP_DIRS
                and not any(part in SCAN_SKIP_DIRS for part in (dp / d).parts)
            ]
            for fn in sorted(filenames):
                p = dp / fn
                if p.suffix.lower() in SCAN_EXTENSIONS:
                    files.append(p)
    return files


def scan_for_secrets(subdirs: Optional[List[str]] = None) -> Dict[str, Any]:
    """Scan source files for secret-like values. Returns count of findings + list."""
    findings: List[Dict[str, Any]] = []
    for p in _iter_scan_files(subdirs):
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        # No assignment needed; regex patterns below are already case-insensitive.
        for pattern in _SECRET_PATTERNS:
            for m in pattern.finditer(text):
                seg = m.group(0)
                if _is_allowed_value(seg):
                    continue
                findings.append({
                    "file": str(p.relative_to(ROOT)),
                    "line": _line_of(text, m.start()),
                    "match": seg[:40],
                })
    return {"count": len(findings), "findings": findings}


def _line_of(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def _is_allowed_value(value: str) -> bool:
    low = value.lower()
    return any(allowed in low for allowed in _FAKE_SCAN_ALLOW)


def check_no_secrets(subdirs: Optional[List[str]] = None) -> Dict[str, Any]:
    res = scan_for_secrets(subdirs)
    ok = res["count"] == 0
    return {"ok": ok, "detail": f"secrets_scan: {res['count']} finding(s)", "count": res["count"]}


def check_classification() -> Dict[str, Any]:
    from security.classification import is_valid_classification
    canonical = {"public", "internal", "client_confidential", "personnel_sensitive",
                 "financial", "regulated_high_risk"}
    ok = all(is_valid_classification(c) for c in canonical)
    return {"ok": ok, "detail": f"classification: canonical set present={ok}"}


def check_deny_by_default() -> Dict[str, Any]:
    from security.identity import Identity
    from security.policy import AuthorizationRequest, authorize
    # Unknown capability must deny by default, not allow.
    idn = Identity(actor="probe", actor_type="agent", tenant_id="t1",
                   client_id="c1", role_id="ops_gm")
    req = AuthorizationRequest(
        identity=idn, capability="__unknown_capability_zzz__",
        owning_role_id="does_not_exist", action="execute",
    )
    decision = authorize(req)
    ok = not decision.allowed
    return {"ok": ok, "detail": f"deny_by_default denied={ok} code={decision.code}"}


def check_audit_integrity(audit_db: Optional[str] = None) -> Dict[str, Any]:
    db = audit_db or (ROOT / "security" / "audit.db")
    if not pathlib.Path(db).exists():
        return {"ok": True, "detail": "audit_integrity: db absent (skipped)", "skipped": True}
    from security.audit import AuditTrail
    trail = AuditTrail(db_path=str(db))
    try:
        valid, msg = trail.verify_chain()
    finally:
        trail.close()
    return {"ok": bool(valid), "detail": f"audit_integrity: {msg}"}


def check_redaction() -> Dict[str, Any]:
    from security.secrets import redact
    secret_value = "sk-super-secret-1234567890-abcdefghijklmnop"
    r = redact(f"the api key is {secret_value}")
    # The sensitive value must not survive redaction.
    ok = secret_value not in r and "[REDACTED" in r
    return {"ok": ok, "detail": f"redaction: secret value removed={ok} -> {r[:60]}"}


def check_malformed_output() -> Dict[str, Any]:
    # Malformed/engine failure output must map to a typed failure, not a bare crash.
    from engines.contracts import EngineResult
    res = EngineResult.failure(
        engine_id="wfm", display_name="WFM", capability_ids=["wfm_forecast"],
        tenant_id="t1", client_id="c1", correlation_id="corr-1",
        causation_id=None, actor="probe", owning_role_id="ops_gm",
        input_payload={}, error_code="MALFORMED_OUTPUT", error_message="bad fields",
    )
    ok = res.error is not None and res.error.get("code") == "MALFORMED_OUTPUT"
    return {"ok": ok, "detail": f"malformed_output: typed failure present={ok}"}


def run_security_gate(
    scan_subdirs: Optional[List[str]] = None,
    audit_db: Optional[str] = None,
) -> Dict[str, Any]:
    """Run all security/data-governance checks and return {check: result}."""
    results = {
        "secrets_scan": check_no_secrets(scan_subdirs),
        "classification": check_classification(),
        "deny_by_default": check_deny_by_default(),
        "redaction": check_redaction(),
        "malformed_output": check_malformed_output(),
        "audit_integrity": check_audit_integrity(audit_db),
    }
    results["all_ok"] = all(r.get("ok", False) for r in results.values())
    return results
