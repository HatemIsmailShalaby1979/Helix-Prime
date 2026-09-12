"""
Streamlit cockpit console entry point (secondary surface).

Launches the read-only Streamlit dashboard. The API spine is the canonical
deployable artifact; this script exists so the dashboard stays reachable
from the installed wheel the same way launch.py reaches it from a checkout.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main() -> int:
    cockpit_app = Path(__file__).resolve().parent / "cockpit.py"
    return subprocess.call(
        [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            str(cockpit_app),
            "--server.headless=true",
            "--server.address=127.0.0.1",
        ]
    )


if __name__ == "__main__":
    raise SystemExit(main())