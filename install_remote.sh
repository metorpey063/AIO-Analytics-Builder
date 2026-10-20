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

    # Remove generated launcher files that conflict with git pull
    # (these get recreated at the end of every install/update)
    for f in "AIO Builder.command" "AIO_Builder.command" "Install AIO.command" "Install_AIO.command"; do
        [ -f "$INSTALL_DIR/$f" ] && rm -f "$INSTALL_DIR/$f"
    done

    git fetch origin main
    git reset --hard origin/main
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

# Look for existing config.json in common locations and copy it over
if [ ! -f "config.json" ] || [ "$(python3 -c "import json; print(len(json.loads(open('config.json').read()).get('profiles',{})))" 2>/dev/null)" = "0" ]; then
    SEARCH_PATHS=(
        "$HOME/Desktop/AIO Analytics Builder/config.json"
        "$HOME/Desktop/AIO-Analytics-Builder/config.json"
        "$HOME/Documents/AIO Analytics Builder/config.json"
        "$HOME/AIO Analytics Builder/config.json"
    )
    for sp in "${SEARCH_PATHS[@]}"; do
        if [ -f "$sp" ] && [ "$sp" != "$INSTALL_DIR/config.json" ]; then
            PROFILE_COUNT=$(python3 -c "import json; print(len(json.loads(open('$sp').read()).get('profiles',{})))" 2>/dev/null)
            if [ "$PROFILE_COUNT" -gt 0 ] 2>/dev/null; then
                log "Found existing config with $PROFILE_COUNT profiles at: $sp"
                cp "$sp" "$INSTALL_DIR/config.json"
                log "Connection profiles restored!"
                break
            fi
        fi
    done
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

# Copy the .app launcher to Desktop (if it exists in the repo)
if [ -d "$INSTALL_DIR/AIO Builder.app" ]; then
    cp -R "$INSTALL_DIR/AIO Builder.app" "$HOME/Desktop/AIO Builder.app" 2>/dev/null
    xattr -cr "$HOME/Desktop/AIO Builder.app" 2>/dev/null
    log "Added 'AIO Builder' app to Desktop"
fi

# Also create the .command fallback
LAUNCHER="$INSTALL_DIR/AIO Builder.command"
cat > "$LAUNCHER" << 'SCRIPT'
#!/bin/bash
cd "$(dirname "$0")"
lsof -ti:5100 2>/dev/null | xargs kill 2>/dev/null
source .venv/bin/activate
echo ""
echo "  AIO Analytics Builder — http://localhost:5100"
echo "  Press Ctrl+C to stop."
echo ""
open "http://localhost:5100"
python3 web-ui/app.py
SCRIPT
chmod +x "$LAUNCHER"

log "Setup complete!"
echo ""
echo -e "  ${GREEN}${BOLD}✓ AIO Analytics Builder is ready${RESET}"
echo ""
echo "  Opening Web UI at http://localhost:5100"
echo "  Press Ctrl+C to stop the server."
echo ""
echo -e "  ${BOLD}To launch again later:${RESET}"
echo "    Double-click 'AIO Builder' on your Desktop"
echo ""

# Launch
open "http://localhost:5100"
.venv/bin/python web-ui/app.py
