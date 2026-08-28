#!/usr/bin/env python3
"""
Helix Prime Codex C8 — local health/readiness command.

Usage:
    python3 scripts/health_check.py

Prints local component readiness (control-plane, audit, registries, filesystem,
Ollama optional) and exits 0 when the required components are ready.
"""
from __future__ import annotations

import json
import sys
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from release import observability  # noqa: E402  (repo-root inserted above)


def main() -> int:
    rep = observability.run_observability_report()
    print(json.dumps(rep["checks"], default=str, indent=2))
    ready = rep["all_ok"]
    print(f"\nREADY={ready} (required components; Ollama optional)")
    return 0 if ready else 1


if __name__ == "__main__":
    sys.exit(main())
