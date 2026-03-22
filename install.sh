#!/bin/bash
# install.sh — Install claude-tg-bridge as the `claude-tg` command
#
# Usage: ./install.sh

set -euo pipefail

INSTALL_DIR="${HOME}/.local/share/claude-tg-bridge"
BIN_DIR="${HOME}/.local/bin"
LINK="${BIN_DIR}/claude-tg"
SOURCE_DIR="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"

echo "Installing claude-tg-bridge..."

# ─── Copy files to install dir ───────────────────────────────────────────────

mkdir -p "$INSTALL_DIR"
cp "$SOURCE_DIR/start.sh"            "$INSTALL_DIR/start.sh"
cp "$SOURCE_DIR/tg_bridge.py"        "$INSTALL_DIR/tg_bridge.py"
cp "$SOURCE_DIR/send-to-telegram.sh" "$INSTALL_DIR/send-to-telegram.sh"
chmod +x "$INSTALL_DIR/start.sh"
chmod +x "$INSTALL_DIR/send-to-telegram.sh"

echo "  Files copied to $INSTALL_DIR"

# ─── Create symlink ─────────────────────────────────────────────────────────

mkdir -p "$BIN_DIR"
ln -sf "$INSTALL_DIR/start.sh" "$LINK"

echo "  Symlink created: $LINK -> $INSTALL_DIR/start.sh"

# ─── Verify PATH ────────────────────────────────────────────────────────────

if ! echo "$PATH" | tr ':' '\n' | grep -qx "$BIN_DIR"; then
  echo ""
  echo "  WARNING: $BIN_DIR is not in your PATH."
  echo "  Add this to your shell profile (~/.bashrc or ~/.zshrc):"
  echo ""
  echo "    export PATH=\"\$HOME/.local/bin:\$PATH\""
  echo ""
fi

echo ""
echo "Done! Run 'claude-tg' from any project directory."
echo "Usage: claude-tg [/path/to/project]   (defaults to current directory)"
