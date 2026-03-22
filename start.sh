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

# Derive unique session name from project directory (sanitize for tmux)
PROJECT_NAME="$(basename "$PROJECT_DIR")"
SESSION="claude-${PROJECT_NAME//[^a-zA-Z0-9_-]/_}"

# ─── Load .env if present ────────────────────────────────────────────────────

ENV_FILE="$SCRIPT_DIR/.env"
if [[ -f "$ENV_FILE" ]]; then
  source "$ENV_FILE"
fi

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

# ─── Kill other claude-tg sessions ───────────────────────────────────────────
# Only one Telegram bridge can be active at a time (shared bot token).
# Multiple bridges cause duplicate message delivery to all projects.

for old_session in $(tmux list-sessions -F '#{session_name}' 2>/dev/null | grep '^claude-'); do
  if [[ "$old_session" != "$SESSION" ]]; then
    echo "[FIX] 🧹 Closing old session '$old_session' (only one bridge allowed)"
    tmux kill-session -t "$old_session"
  fi
done

# ─── tmux: Claude Code window ────────────────────────────────────────────────

if tmux has-session -t "$SESSION" 2>/dev/null; then
  echo "ℹ️  Session '$SESSION' already exists, connecting..."
  # Recreate the "code" window if it was closed (e.g. claude exited)
  if ! tmux list-windows -t "$SESSION" | grep -q "code"; then
    echo "🔄 Recreating window 'code' → Claude Code"
    tmux new-window -t "${SESSION}:" -n "code" -c "$PROJECT_DIR" "claude"
  fi
else
  echo "🚀 Creating tmux session '$SESSION' → window 0: Claude Code"
  tmux new-session -d -s "$SESSION" -n "code" -c "$PROJECT_DIR" "claude"
fi

# ─── tmux: bridge window ─────────────────────────────────────────────────────

if tmux list-windows -t "$SESSION" | grep -q "bridge"; then
  echo "🔄 Killing old bridge window..."
  tmux kill-window -t "${SESSION}:bridge"
fi
echo "🤖 Creating window 'bridge' → Python bridge"
tmux new-window -t "${SESSION}:" -n "bridge" \
  "cd '$SCRIPT_DIR' && TMUX_TARGET='${SESSION}:code' uv run tg_bridge.py; exec bash"

# ─── Attach to Claude window ─────────────────────────────────────────────────

echo ""
echo "✅ Done!"
echo "   Claude Code : tmux attach -t ${SESSION}:code"
echo "   Bridge logs : tmux select-window -t ${SESSION}:bridge"
echo ""
echo "Connecting to session..."
tmux attach -t "${SESSION}:code"
