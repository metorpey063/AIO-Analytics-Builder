#!/bin/bash
# ──────────────────────────────────────────────────────────
# Install the Salesforce CLI (`sf`) if it's missing.
#
# The Web UI's "Salesforce: Automatic Setup" (org_bootstrap.py) needs it.
# Called by install_remote.sh, AIO Installer.app, install.py and the
# AIO Builder launcher. Best effort: always exits 0 so it never blocks
# an install or launch. Manual setup still works without the CLI.
# ──────────────────────────────────────────────────────────

export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"

GREEN="\033[92m"
YELLOW="\033[93m"
BOLD="\033[1m"
RESET="\033[0m"
log() { echo -e "${GREEN}${BOLD}  → ${RESET}$1"; }
warn() { echo -e "${YELLOW}${BOLD}  ⚠ ${RESET}$1"; }

if command -v sf &>/dev/null; then
    log "Salesforce CLI found ($(sf --version 2>/dev/null | head -1 | cut -d' ' -f1))"
    exit 0
fi

if command -v brew &>/dev/null; then
    log "Installing the Salesforce CLI (brew install sf, takes a minute or two)..."
    if brew install sf >/dev/null 2>&1 && command -v sf &>/dev/null; then
        log "Salesforce CLI installed"
        exit 0
    fi
    warn "brew install sf failed."
elif command -v npm &>/dev/null; then
    log "Installing the Salesforce CLI (npm install -g @salesforce/cli)..."
    if npm install -g @salesforce/cli >/dev/null 2>&1 && command -v sf &>/dev/null; then
        log "Salesforce CLI installed"
        exit 0
    fi
    warn "npm install -g @salesforce/cli failed."
fi

warn "Salesforce CLI not installed. Salesforce Automatic Setup needs it."
if ! command -v brew &>/dev/null; then
    [ "$(uname -m)" = "arm64" ] && ARCH=arm64 || ARCH=x64
    PKG_URL="https://developer.salesforce.com/media/salesforce-cli/sf/channels/stable/sf-$ARCH.pkg"
    # Open the official installer once (it asks for the Mac password itself); after that just print the link
    MARKER="$(cd "$(dirname "$0")" && pwd)/.sf_pkg_offered"
    PKG="${TMPDIR:-/tmp}/sf-$ARCH.pkg"
    if [ "$(uname)" = "Darwin" ] && [ ! -f "$MARKER" ]; then
        log "Downloading the Salesforce CLI installer..."
        if curl -fsSL -o "$PKG" "$PKG_URL"; then
            touch "$MARKER"
            open "$PKG"
            log "Opened the Salesforce CLI installer. Click through it, then quit and relaunch AIO Builder."
            exit 0
        fi
        warn "Download failed."
    fi
    echo "    Download and open the installer (no Homebrew needed):"
    echo "      $PKG_URL"
    echo "    then relaunch AIO Builder."
else
    echo "    Install it with:  brew install sf"
fi
echo "    (Manual setup in the Web UI works without it.)"
exit 0
