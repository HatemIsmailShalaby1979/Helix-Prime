"""Deterministic constitutional and repository-governance checks.

This check is intentionally dependency-free and read-only. It blocks drift in
agent sessions without treating narrative documents as proof of implementation.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parent.parent
CONSTITUTION = ROOT / "00_CONSTITUTION.md"
MASTER_STORY = ROOT / "MASTER_STORY.md"

REQUIRED_CONSTITUTION_LINES = (
    "Identity must precede implementation.",
    "Truth is paramount.",
    "Architecture serves as the expression of truth.",
)

STALE_AUTHORITY_REFERENCES = ("ROOT_BOOT.md", "constitution_v0.md")


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def check_constitution() -> dict[str, object]:
    if not CONSTITUTION.exists():
        return {"ok": False, "detail": "missing 00_CONSTITUTION.md"}
    text = _read(CONSTITUTION)
    missing = [line for line in REQUIRED_CONSTITUTION_LINES if line not in text]
    if missing:
        return {"ok": False, "detail": f"constitution missing required principles: {missing}"}
    return {"ok": True, "detail": "Constitution 000 present and contains required principles"}


def check_master_story_authority() -> dict[str, object]:
    if not MASTER_STORY.exists():
        return {"ok": False, "detail": "missing MASTER_STORY.md"}
    text = _read(MASTER_STORY)
    if "00_CONSTITUTION.md" not in text:
        return {"ok": False, "detail": "MASTER_STORY.md does not reference 00_CONSTITUTION.md"}
    return {"ok": True, "detail": "MASTER_STORY.md references Constitution 000"}


def check_stale_authority_references(paths: Iterable[Path] | None = None) -> dict[str, object]:
    scan_paths = list(paths or [ROOT / "README.md", ROOT / "CONTRIBUTING.md", ROOT / "MASTER_STORY.md", ROOT / "GOVERNANCE"])
    findings: list[str] = []
    for path in scan_paths:
        if path.is_dir():
            candidates = path.rglob("*.md")
        else:
            candidates = [path]
        for candidate in candidates:
            if not candidate.exists():
                continue
            text = _read(candidate)
            for stale in STALE_AUTHORITY_REFERENCES:
                if stale in text and "historical" not in text.lower():
                    try:
                        display_path = candidate.relative_to(ROOT)
                    except ValueError:
                        display_path = candidate
                    findings.append(f"{display_path} references {stale}")
    return {"ok": not findings, "detail": "no stale authority references" if not findings else "; ".join(findings)}


def run_checks() -> dict[str, object]:
    checks = {
        "constitution": check_constitution(),
        "master_story_authority": check_master_story_authority(),
        "stale_authority_references": check_stale_authority_references(),
    }
    return {"checks": checks, "all_ok": all(item["ok"] for item in checks.values())}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("check", "json"), nargs="?", default="check")
    args = parser.parse_args()
    result = run_checks()
    if args.command == "json":
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        for name, check in result["checks"].items():
            print(f"{'PASS' if check['ok'] else 'FAIL'} {name}: {check['detail']}")
        print(f"governance={'PASS' if result['all_ok'] else 'FAIL'}")
    return 0 if result["all_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
