#!/usr/bin/env bash
# Helix Prime - Linux/macOS setup
# Creates a local virtual environment, installs cockpit dependencies, and fails clearly
# on any error. Uses `if [ ! -f ".venv/bin/activate" ]` (never an executable-permission check).
set -euo pipefail

echo "============================================"
echo "  Helix Prime - Linux/macOS Setup"
echo "============================================"

# --- Require Python 3.11+ ---
PYTHON_BIN="$(command -v python3 || true)"
if [ -z "$PYTHON_BIN" ]; then
  echo "ERROR: python3 was not found in PATH. Install Python 3.11+ and retry." >&2
  exit 1
fi

PY_MAJOR="$("$PYTHON_BIN" -c 'import sys; print(sys.version_info[0])')"
PY_MINOR="$("$PYTHON_BIN" -c 'import sys; print(sys.version_info[1])')"
if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 11 ]; }; then
  PY_VER="$("$PYTHON_BIN" -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
  echo "ERROR: Helix Prime requires Python 3.11 or newer (found $PY_VER)." >&2
  exit 1
fi
echo "[1/3] Using $("$PYTHON_BIN" -c 'import sys; print("%d.%d" % sys.version_info[:2])') at $PYTHON_BIN"

# --- Create virtual environment only if it does not already exist ---
if [ ! -f ".venv/bin/activate" ]; then
  echo "[2/3] Creating virtual environment (.venv)..."
  "$PYTHON_BIN" -m venv .venv || { echo "ERROR: failed to create .venv" >&2; exit 1; }
else
  echo "[2/3] Reusing existing .venv"
fi

# --- Activate and install dependencies ---
# shellcheck disable=SC1091
source .venv/bin/activate
echo "[3/3] Installing dependencies from cockpit/requirements.txt..."
pip install -r cockpit/requirements.txt || { echo "ERROR: failed to install dependencies" >&2; exit 1; }

echo "============================================"
echo "  Setup complete."
echo "  Launch the cockpit with:  python launch.py"
echo "  (or: source .venv/bin/activate && streamlit run cockpit/cockpit.py)"
echo "============================================"
