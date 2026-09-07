#!/usr/bin/env python
"""
C0 dependency drift check.

The repository used to carry five overlapping manifests (cockpit/, engines/b2b/,
engines/cx/, marketing/, release/). They drifted, and the drift was invisible
until something failed at runtime. This script makes drift a build failure.

Checks
------
1. No manifest outside requirements.txt / requirements-dev.txt declares a
   distribution that is not present in the canonical set.
2. No manifest declares a conflicting bound for a distribution that is in the
   canonical set (e.g. pandas>=2.0 in one file, pandas<2.0 in another).
3. Every structural and data-processing dependency is declared exactly once at
   the canonical level.

Exit code 0 = no drift. Exit code 1 = drift found (CI fails).

Usage
-----
    python scripts/check_dependencies.py
    python scripts/check_dependencies.py --json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent

CANONICAL = REPO_ROOT / "requirements.txt"
CANONICAL_DEV = REPO_ROOT / "requirements-dev.txt"

#: Manifests allowed to exist. Anything else is drift by definition.
ALLOWED_MANIFESTS = {
    CANONICAL,
    CANONICAL_DEV,
    REPO_ROOT / "release" / "requirements.lock.txt",
}

#: Directories never scanned (vendored, virtualenvs, caches).
SKIP_DIRS = {
    ".git",
    ".venv",
    ".venv-win",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    "__pycache__",
    "node_modules",
    ".workbuddy-ai",
    "src-tauri",
}

_REQUIREMENT_RE = re.compile(
    r"^(?P<name>[A-Za-z0-9][A-Za-z0-9._-]*)\s*(?P<spec>[<>=!~].*)?$"
)
_SKIP_PREFIXES = ("-r ", "--", "#")


def normalise(name: str) -> str:
    """PEP 503 normalisation: lowercase, runs of -_. collapsed to a single dash."""
    return re.sub(r"[-_.]+", "-", name).strip().lower()


def parse_manifest(path: Path) -> Dict[str, str]:
    """Return {normalised_name: specifier_string} for a requirements file."""
    out: Dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith(_SKIP_PREFIXES):
            continue
        # Strip inline comments and environment markers.
        line = line.split(" #", 1)[0].strip()
        line = line.split(";", 1)[0].strip()
        match = _REQUIREMENT_RE.match(line)
        if not match:
            continue
        name = normalise(match.group("name"))
        spec = (match.group("spec") or "").replace(" ", "")
        out[name] = spec
    return out


def find_manifests() -> List[Path]:
    found: List[Path] = []
    for path in REPO_ROOT.rglob("*requirements*.txt"):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        found.append(path)
    for path in REPO_ROOT.rglob("requirements*.txt"):
        if path not in found and not any(part in SKIP_DIRS for part in path.parts):
            found.append(path)
    return sorted(set(found))


def bounds_conflict(a: str, b: str) -> bool:
    """
    Conservative conflict test between two PEP 440 specifier sets.

    Compares the numeric part of paired lower/upper bounds. Deliberately
    conservative: it flags only unambiguous contradictions (a lower bound at or
    above an opposing upper bound), so it never produces a false failure on
    compatible ranges.
    """
    lower_a = _extract(a, ">=")
    upper_a = _extract(a, "<")
    lower_b = _extract(b, ">=")
    upper_b = _extract(b, "<")
    if lower_a is not None and upper_b is not None and lower_a >= upper_b:
        return True
    if lower_b is not None and upper_a is not None and lower_b >= upper_a:
        return True
    return False


def _extract(spec: str, operator: str) -> Optional[Tuple[int, ...]]:
    match = re.search(re.escape(operator) + r"\s*([0-9][0-9A-Za-z.+!]*)", spec)
    if not match:
        return None
    parts: List[int] = []
    for chunk in match.group(1).split("."):
        digits = re.match(r"\d+", chunk)
        if not digits:
            break
        parts.append(int(digits.group(0)))
    return tuple(parts) if parts else None


def check() -> Tuple[List[str], List[str]]:
    """Return (errors, warnings)."""
    errors: List[str] = []
    warnings: List[str] = []

    if not CANONICAL.exists():
        return [f"canonical manifest missing: {CANONICAL}"], warnings

    canonical = parse_manifest(CANONICAL)
    canonical_dev = parse_manifest(CANONICAL_DEV) if CANONICAL_DEV.exists() else {}
    combined = {**canonical, **canonical_dev}

    manifests = find_manifests()
    for manifest in manifests:
        rel = manifest.relative_to(REPO_ROOT).as_posix()
        declared = parse_manifest(manifest)
        # C0 leaves empty compatibility shims in historical subdirectories so
        # old install commands fail visibly rather than silently installing a
        # stale dependency graph. An empty shim is compliant; a new package in
        # it is drift.
        if manifest not in ALLOWED_MANIFESTS:
            if not declared:
                continue
            errors.append(
                f"{rel}: manifest is not in the allowed set "
                f"({sorted(p.relative_to(REPO_ROOT).as_posix() for p in ALLOWED_MANIFESTS)}); "
                "fold it into requirements.txt and delete it"
            )
            continue


        if manifest == CANONICAL:
            continue

        for name, spec in sorted(declared.items()):
            if name not in combined:
                errors.append(
                    f"{rel}: declares '{name}{spec}' which is absent from the canonical set"
                )
                continue
            canon_spec = combined[name]
            if canon_spec and spec and bounds_conflict(canon_spec, spec):
                errors.append(
                    f"{rel}: '{name}{spec}' conflicts with canonical bound '{name}{canon_spec}'"
                )

    # Structural + data-processing dependencies must be present.
    required = ["pydantic", "pandas", "numpy"]
    for name in required:
        if name not in canonical:
            errors.append(f"requirements.txt: mandatory dependency '{name}' is not declared")

    # sqlite3 is stdlib: it must never appear as an installable requirement.
    if "sqlite3" in canonical or "sqlite" in canonical:
        errors.append(
            "requirements.txt: sqlite3 is CPython stdlib and must not be declared as a "
            "distribution; document it as a comment instead"
        )

    if not (REPO_ROOT / "release" / "requirements.lock.txt").exists():
        warnings.append("release/requirements.lock.txt is missing — regenerate it")
    else:
        lock = parse_manifest(REPO_ROOT / "release" / "requirements.lock.txt")
        for name, spec in sorted(lock.items()):
            if name in canonical and bounds_conflict(canonical[name], spec):
                warnings.append(
                    f"release/requirements.lock.txt: '{name}{spec}' is outside canonical "
                    f"bound '{name}{canonical[name]}' — regenerate the lock"
                )

    return errors, warnings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit machine-readable output")
    args = parser.parse_args()

    errors, warnings = check()

    if args.json:
        print(json.dumps({"errors": errors, "warnings": warnings}, indent=2))
    else:
        if warnings:
            print("Dependency warnings:")
            for w in warnings:
                print(f"  WARN  {w}")
        if errors:
            print("Dependency drift detected:")
            for e in errors:
                print(f"  ERROR {e}")
        if not errors and not warnings:
            print("Dependency check passed: no drift across manifests.")

    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
