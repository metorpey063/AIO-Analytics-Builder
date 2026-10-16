#!/bin/bash
# ──────────────────────────────────────────
# AIO Analytics Builder — One-Click Install
# Double-click this file to set up AIO.
# ──────────────────────────────────────────

cd "$(dirname "$0")"

echo ""
echo "  ┌─────────────────────────────────────────┐"
echo "  │       AIO Analytics Builder Setup        │"
echo "  │                                          │"
echo "  │  Tableau Pulse · Tableau Next · Data Cloud│"
echo "  └─────────────────────────────────────────┘"
echo ""

# Check for Python 3
if command -v python3 &>/dev/null; then
    PYTHON=python3
elif command -v python &>/dev/null; then
    PYTHON=python
else
    echo "  ✗ Python 3 not found."
    echo ""
    echo "  Install Python 3.10+ from https://www.python.org/downloads/"
    echo "  or run: brew install python3"
    echo ""
    read -p "  Press Enter to exit..."
    exit 1
fi

PY_VERSION=$($PYTHON -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo "  → Python $PY_VERSION found"

# Check minimum version
PY_OK=$($PYTHON -c "import sys; print(1 if sys.version_info >= (3, 10) else 0)")
if [ "$PY_OK" != "1" ]; then
    echo "  ✗ Python 3.10+ is required (found $PY_VERSION)"
    echo "  Install from https://www.python.org/downloads/"
    read -p "  Press Enter to exit..."
    exit 1
fi

# Run the installer
$PYTHON install.py

# If the installer exits (server stopped), keep the window open briefly
echo ""
echo "  Server stopped."
read -p "  Press Enter to close..."
