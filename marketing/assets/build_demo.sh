#!/usr/bin/env bash
# build_demo.sh — Build the Helix Prime 5-minute demo video.
#
# Usage:
#   ./build_demo.sh           # build and emit assets/Helix_Prime_5Min_Demo.mp4
#
# Requires Python 3.10+. Will pip-install requirements-demo.txt into the
# current environment if missing.

set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"

echo "[build_demo] Python: $(python --version 2>&1)"
echo "[build_demo] CWD: $HERE"

if ! python -c "import edge_tts, imageio_ffmpeg, PIL" >/dev/null 2>&1; then
  echo "[build_demo] Installing requirements..."
  python -m pip install -r "$ROOT/requirements-demo.txt"
fi

python "$HERE/build_demo.py"
