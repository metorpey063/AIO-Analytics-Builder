#!/bin/bash
# ──────────────────────────────────────────────────────────
# AIO Analytics Builder — Remote One-Line Installer
#
# Usage:  curl -sL https://raw.githubusercontent.com/metorpey063/AIO-Analytics-Builder/main/install_remote.sh | bash
#
# What this does:
#   1. Clones the repo to ~/AIO-Analytics-Builder
#   2. Strips macOS quarantine flags (no Gatekeeper popups)
#   3. Creates a Python virtual environment
#   4. Installs all dependencies
#   5. Launches the Web UI at http://localhost:5050
# ──────────────────────────────────────────────────────────

set -e

GREEN="\033[92m"
BOLD="\033[1m"
RESET="\033[0m"

log() { echo -e "${GREEN}${BOLD}  → ${RESET}$1"; }

echo ""
echo -e "${BOLD}  ┌─────────────────────────────────────────┐"
echo "  │       AIO Analytics Builder Setup        │"
echo "  │                                          │"
echo "  │  Tableau Pulse · Tableau Next · Data Cloud│"
echo -e "  └─────────────────────────────────────────┘${RESET}"
echo ""

INSTALL_DIR="$HOME/AIO-Analytics-Builder"

# Check Python 3.10+
if ! command -v python3 &>/dev/null; then
    echo "  ✗ Python 3 not found. Install from https://www.python.org/downloads/"
    exit 1
fi

PY_OK=$(python3 -c "import sys; print(1 if sys.version_info >= (3, 10) else 0)")
if [ "$PY_OK" != "1" ]; then
    echo "  ✗ Python 3.10+ required. Install from https://www.python.org/downloads/"
    exit 1
fi
log "Python 3 found"

# Clone or update
if [ -d "$INSTALL_DIR/.git" ]; then
    log "Updating existing installation..."
    cd "$INSTALL_DIR"
    git pull --ff-only origin main 2>/dev/null || git pull origin main
else
    log "Downloading AIO Analytics Builder..."
    git clone https://github.com/metorpey063/AIO-Analytics-Builder.git "$INSTALL_DIR"
    cd "$INSTALL_DIR"
fi

# Strip macOS quarantine (prevents Gatekeeper popups)
if [ "$(uname)" = "Darwin" ]; then
    log "Clearing macOS quarantine flags..."
    xattr -cr "$INSTALL_DIR" 2>/dev/null || true
fi

# Create venv + install deps
if [ ! -d ".venv" ]; then
    log "Creating virtual environment..."
    python3 -m venv .venv
fi

log "Installing dependencies..."
.venv/bin/pip install --upgrade pip -q
.venv/bin/pip install -r requirements.txt -q

# Create config if needed
if [ ! -f "config.json" ] && [ -f "config.json.template" ]; then
    cp config.json.template config.json
    log "Created config.json"
fi

# Create double-click launcher
LAUNCHER="$INSTALL_DIR/AIO Builder.command"
cat > "$LAUNCHER" << 'SCRIPT'
#!/bin/bash
cd "$(dirname "$0")"
if [ ! -d ".venv" ]; then
    echo "Virtual environment not found. Run the installer first."
    read -p "Press Enter to exit..."
    exit 1
fi
source .venv/bin/activate
echo ""
echo "  AIO Analytics Builder"
echo "  Starting web server..."
echo ""
python3 web-ui/app.py
SCRIPT
chmod +x "$LAUNCHER"
log "Created 'AIO Builder.command' — double-click to launch next time"

# Create a Desktop shortcut so it's easy to find
DESKTOP_SHORTCUT="$HOME/Desktop/AIO Builder.command"
if [ ! -f "$DESKTOP_SHORTCUT" ]; then
    cat > "$DESKTOP_SHORTCUT" << SHORTCUT
#!/bin/bash
cd "$INSTALL_DIR"
source .venv/bin/activate
python3 web-ui/app.py
SHORTCUT
    chmod +x "$DESKTOP_SHORTCUT"
    log "Added 'AIO Builder' shortcut to Desktop"
fi

log "Setup complete!"
echo ""
echo -e "  ${GREEN}${BOLD}✓ AIO Analytics Builder is ready${RESET}"
echo ""
echo "  Opening Web UI at http://localhost:5050"
echo "  Press Ctrl+C to stop the server."
echo ""
echo -e "  ${BOLD}To launch again later:${RESET}"
echo "    Double-click 'AIO Builder' on your Desktop"
echo ""

# Launch
.venv/bin/python web-ui/app.py
