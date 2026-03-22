#!/bin/bash
# ~/claude-tg-bridge/start.sh
#
# Launches Claude Code in a tmux session "claude",
# then starts the Python bridge in a separate window.
#
# Usage: ./start.sh [/path/to/project]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"
PROJECT_DIR="${1:-$(pwd)}"
SESSION="claude"

# ─── Checks ──────────────────────────────────────────────────────────────────

for cmd in tmux uv; do
  if ! command -v "$cmd" &>/dev/null; then
    echo "❌  '$cmd' not found. Install: sudo apt install $cmd  (or 'pip install uv')"
    exit 1
  fi
done

if [[ -z "${TELEGRAM_BOT_TOKEN:-}" || -z "${TELEGRAM_CHAT_ID:-}" ]]; then
  echo "❌  Set environment variables:"
  echo "    export TELEGRAM_BOT_TOKEN=your_token"
  echo "    export TELEGRAM_CHAT_ID=your_chat_id"
  exit 1
fi

# ─── tmux: Claude Code window ────────────────────────────────────────────────

if tmux has-session -t "$SESSION" 2>/dev/null; then
  echo "ℹ️  Session '$SESSION' already exists, connecting..."
else
  echo "🚀 Creating tmux session '$SESSION' → window 0: Claude Code"
  tmux new-session -d -s "$SESSION" -n "code" -c "$PROJECT_DIR" "claude"
fi

# ─── tmux: bridge window ─────────────────────────────────────────────────────

if ! tmux list-windows -t "$SESSION" | grep -q "bridge"; then
  echo "🤖 Creating window 'bridge' → Python bridge"
  tmux new-window -t "${SESSION}:" -n "bridge" \
    "cd '$SCRIPT_DIR' && uv run tg_bridge.py; exec bash"
fi

# ─── Attach to Claude window ─────────────────────────────────────────────────

echo ""
echo "✅ Done!"
echo "   Claude Code : tmux attach -t ${SESSION}:0"
echo "   Bridge logs : tmux select-window -t ${SESSION}:bridge"
echo ""
echo "Connecting to session..."
tmux attach -t "${SESSION}:0"
