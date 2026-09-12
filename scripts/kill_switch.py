#!/usr/bin/env python3
"""
Helix Codex OS kill switch CLI (H1.5, G18).

Engage, release, or inspect the emergency halt honored by the control plane
before every committal action. Operates on the same persisted flag the engine
reads; the running service sees the engagement on its next committal action
(SQLite is the persistence, no sidecar).

Usage:
    python scripts/kill_switch.py engage --reason "..." [--actor NAME] [--tenant ID]
    python scripts/kill_switch.py release [--actor NAME] [--tenant ID]
    python scripts/kill_switch.py status [--tenant ID]

Paths default to the service defaults (control_plane/workflow.db and
security/audit.db); override with --db-path / --audit-db-path. Exit 0 on
success; argparse usage errors exit 2; operational failures exit 1.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from control_plane.kill_switch import KillSwitch  # noqa: E402


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="kill_switch",
        description="Helix Codex OS emergency halt: engage, release, or inspect.",
    )
    parser.add_argument("--db-path", default="control_plane/workflow.db")
    parser.add_argument("--audit-db-path", default="security/audit.db")
    sub = parser.add_subparsers(dest="command", required=True)

    engage_parser = sub.add_parser("engage", help="halt the platform (or one tenant)")
    engage_parser.add_argument("--reason", required=True)
    engage_parser.add_argument("--actor", default="operator")
    engage_parser.add_argument("--tenant", default=None)

    release_parser = sub.add_parser("release", help="lift the halt")
    release_parser.add_argument("--actor", default="operator")
    release_parser.add_argument("--tenant", default=None)

    status_parser = sub.add_parser("status", help="show halt state")
    status_parser.add_argument("--tenant", default=None)

    args = parser.parse_args(argv)
    switch = KillSwitch(db_path=args.db_path, audit_db_path=args.audit_db_path)
    try:
        if args.command == "engage":
            result = switch.engage(args.reason, args.actor, tenant_id=args.tenant)
        elif args.command == "release":
            result = switch.release(args.actor, tenant_id=args.tenant)
        else:
            result = switch.status(tenant_id=args.tenant)
        print(json.dumps(result, indent=2))
        return 0
    except ValueError as exc:
        print(f"kill_switch: invalid request: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"kill_switch: operation failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
