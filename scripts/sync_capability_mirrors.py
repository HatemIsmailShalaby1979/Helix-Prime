#!/usr/bin/env python3
"""
Capability-registry mirror generator (A2.3).

The organization model has one authored capability registry and two derived views:

  canonical : organization/capability-registry.yaml  — engine capability -> engine
  mirror    : contracts/capabilities.yaml            — YAML view
  mirror    : organization/capabilities.json         — JSON view

Nothing in the runtime reads the mirrors. ``organization/capability_registry.py``
loads the canonical file directly; the mirrors exist only because consumers expect
those two paths. They used to be hand-maintained copies kept in step by
``validate_mirror_drift()`` — a validator whose entire job was to police a copy that
nothing consumes. This script removes that job: the copies are build artifacts now,
this file is the only thing that writes them, and ``--check`` fails CI when a
committed mirror is stale.

Agent capabilities are deliberately *not* mirrored. They are canonical in
organization/role-catalog.yaml (``owned_capabilities``) and merged at load time.

Output is deterministic: the mirrors carry the canonical file's ``generated`` value
verbatim, so regenerating an unchanged canonical is a no-op. ``generated`` therefore
means "derived from the canonical revision dated X", not "when this script last ran".

Usage:
    python scripts/sync_capability_mirrors.py           # regenerate the mirrors
    python scripts/sync_capability_mirrors.py --check   # fail if a mirror is stale
    python scripts/sync_capability_mirrors.py --check --json

Exit 0 = mirrors current (or written). Exit 1 = stale, missing, or the canonical
could not be read — a control that cannot run fails closed.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

#: The one authored file. Everything else in this module is derived from it.
CANONICAL = "organization/capability-registry.yaml"
YAML_MIRROR = "contracts/capabilities.yaml"
JSON_MIRROR = "organization/capabilities.json"

REGEN_COMMAND = "python scripts/sync_capability_mirrors.py"

#: Marker written into both mirrors so a hand-edit is obvious on sight.
MIRROR_CLASSIFICATION = "C1A_MIRROR"


class CanonicalUnavailableError(RuntimeError):
    """Raised when the canonical capability registry cannot be read."""


def load_canonical() -> dict:
    """
    Read the canonical capability registry.

    Fails closed on a missing, unreadable, malformed or shapeless file rather than
    generating an empty mirror set that would look valid.
    """
    try:
        import yaml  # type: ignore
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise CanonicalUnavailableError(
            "PyYAML not installed: cannot read the canonical capability registry"
        ) from exc

    path = REPO_ROOT / CANONICAL
    if not path.exists():
        raise CanonicalUnavailableError(f"canonical capability registry not found at {CANONICAL}")

    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 - any read failure is fatal for a generator
        raise CanonicalUnavailableError(f"cannot parse {CANONICAL}: {exc}") from exc

    if not isinstance(data, dict):
        raise CanonicalUnavailableError(
            f"{CANONICAL}: top-level must be a mapping, got {type(data).__name__}"
        )
    if not isinstance(data.get("engine_capabilities"), dict):
        raise CanonicalUnavailableError(f"{CANONICAL}: 'engine_capabilities' must be a mapping")
    if data.get("schema_version") is None or data.get("generated") is None:
        raise CanonicalUnavailableError(
            f"{CANONICAL}: 'schema_version' and 'generated' are required so the mirrors "
            f"can be produced deterministically"
        )
    return data


def render_yaml_mirror(canonical: dict) -> str:
    """Render contracts/capabilities.yaml exactly as it should appear on disk."""
    lines = [
        "# Helix Prime — GENERATED MIRROR — DO NOT HAND-EDIT",
        f"# Regenerate with: {REGEN_COMMAND}",
        f"# Canonical: {CANONICAL} (engine_capabilities)",
        f"# This file: {YAML_MIRROR} — YAML view for consumers that expect this path",
        "# Verified current by tests/test_capability_registry_drift.py and by --check in CI.",
        "# Agent capabilities are canonical in organization/role-catalog.yaml (owned_capabilities).",
        f'schema_version: "{canonical["schema_version"]}"',
        f'generated: "{canonical["generated"]}"',
        f'classification: "{MIRROR_CLASSIFICATION}"',
        f'canonical_source: "{CANONICAL}"',
        "",
        "engine_capabilities:",
    ]
    lines.extend(f'  {key}: "{value}"' for key, value in canonical["engine_capabilities"].items())
    lines.extend(
        [
            "",
            "# Agent capabilities reference (do not duplicate — see organization/role-catalog.yaml)",
            'agent_capabilities_source: "organization/role-catalog.yaml"',
            "",
        ]
    )
    return "\n".join(lines)


def render_json_mirror(canonical: dict) -> str:
    """Render organization/capabilities.json exactly as it should appear on disk."""
    payload = {
        "schema_version": canonical["schema_version"],
        "generated": canonical["generated"],
        "classification": MIRROR_CLASSIFICATION,
        "engine_capabilities": dict(canonical["engine_capabilities"]),
        "canonical_source": CANONICAL,
        "note": f"GENERATED MIRROR — do not hand-edit; regenerate with {REGEN_COMMAND}",
    }
    # ensure_ascii keeps the em-dash escaped, so the artifact stays ASCII-clean.
    return json.dumps(payload, indent=2) + "\n"


def _rendered_mirrors(canonical: dict) -> list[tuple[str, str]]:
    return [
        (YAML_MIRROR, render_yaml_mirror(canonical)),
        (JSON_MIRROR, render_json_mirror(canonical)),
    ]


def check_mirrors() -> tuple[list[str], dict]:
    """
    Compare the committed mirrors against what the canonical would generate.

    Byte comparison, because a generated artifact that differs by even a comment is
    not the artifact the generator produces. The report also carries a semantic
    verdict so a formatting-only difference reads differently from a real divergence.
    """
    canonical = load_canonical()
    engine_caps = canonical["engine_capabilities"]

    errors: list[str] = []
    files: dict[str, dict] = {}

    for relative_path, expected in _rendered_mirrors(canonical):
        path = REPO_ROOT / relative_path
        if not path.exists():
            errors.append(f"{relative_path}: mirror is missing; run {REGEN_COMMAND}")
            files[relative_path] = {
                "exists": False,
                "byte_current": False,
                "semantic_current": None,
            }
            continue

        actual = path.read_text(encoding="utf-8")
        byte_current = actual == expected
        files[relative_path] = {"exists": True, "byte_current": byte_current}

        if byte_current:
            files[relative_path]["semantic_current"] = True
            continue

        # Distinguish "the mappings diverged" from "only the wrapper changed".
        try:
            if relative_path.endswith(".json"):
                parsed = json.loads(actual)
            else:
                import yaml  # type: ignore

                parsed = yaml.safe_load(actual)
            semantic_current = (
                isinstance(parsed, dict) and parsed.get("engine_capabilities") == engine_caps
            )
        except Exception:  # noqa: BLE001 - unparseable mirror is simply not current
            semantic_current = False

        files[relative_path]["semantic_current"] = semantic_current
        if semantic_current:
            errors.append(
                f"{relative_path}: engine_capabilities match the canonical but the file is "
                f"not what the generator emits (stale header or formatting); run {REGEN_COMMAND}"
            )
        else:
            errors.append(
                f"{relative_path}: engine_capabilities diverge from the canonical; "
                f"run {REGEN_COMMAND}"
            )

    report = {
        "canonical": CANONICAL,
        "engine_capability_count": len(engine_caps),
        "files": files,
        "errors": errors,
    }
    return errors, report


def write_mirrors() -> dict:
    """Rewrite both mirrors from the canonical. Returns a report of what changed."""
    canonical = load_canonical()
    written: dict[str, str] = {}

    for relative_path, rendered in _rendered_mirrors(canonical):
        path = REPO_ROOT / relative_path
        previous = path.read_text(encoding="utf-8") if path.exists() else None
        if previous == rendered:
            written[relative_path] = "unchanged"
            continue
        path.write_text(rendered, encoding="utf-8", newline="\n")
        written[relative_path] = "created" if previous is None else "rewritten"

    return {
        "canonical": CANONICAL,
        "engine_capability_count": len(canonical["engine_capabilities"]),
        "files": written,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify the mirrors are current instead of rewriting them",
    )
    parser.add_argument("--json", action="store_true", help="emit machine-readable output")
    args = parser.parse_args(argv)

    try:
        if args.check:
            errors, report = check_mirrors()
        else:
            errors, report = [], write_mirrors()
    except Exception as exc:  # noqa: BLE001 - a control that cannot run fails closed
        if args.json:
            print(json.dumps({"errors": [f"mirror sync could not run: {exc}"]}, indent=2))
        else:
            print(f"ERROR mirror sync could not run: {exc}")
        return 1

    if args.json:
        print(json.dumps(report, indent=2))
    elif args.check:
        print(
            f"Capability registry mirrors: {report['engine_capability_count']} engine "
            f"capability mapping(s), checked against {report['canonical']}"
        )
        if errors:
            print("Mirrors are not current:")
            for error in errors:
                print(f"  ERROR {error}")
        else:
            print("Both mirrors are exactly what the canonical generates.")
    else:
        print(
            f"Regenerated capability registry mirrors from {report['canonical']} "
            f"({report['engine_capability_count']} engine capability mapping(s))"
        )
        for relative_path, status in report["files"].items():
            print(f"  {status:9} {relative_path}")

    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
