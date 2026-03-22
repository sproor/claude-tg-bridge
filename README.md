# claude-tg-bridge

Bidirectional bridge between Telegram and [Claude Code](https://docs.anthropic.com/en/docs/claude-code) running in a tmux session.

Send messages from Telegram — they get forwarded to Claude Code as input. Claude's responses are sent back to Telegram automatically.

## Features

- Forward Telegram messages to Claude Code via tmux keystroke injection
- Send Claude Code responses (Stop, Notification, StopFailure) back to Telegram
- Auto-create tmux session with Claude Code + bridge windows
- Dynamic session naming per project (`claude-<project-name>`)
- Single-session policy — kills other bridge sessions to prevent duplicate delivery
- Tmux watchdog — auto-stops the bridge when you detach from the session
- Startup notification sent to Telegram when Claude opens
- Chat authorization — only responds to a configured chat ID
- Respects Telegram's 4096-char message limit

## Prerequisites

- Python 3.10+
- [uv](https://github.com/astral-sh/uv) — Python script runner
- [tmux](https://github.com/tmux/tmux)
- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) CLI installed
- A Telegram bot token (create one via [@BotFather](https://t.me/BotFather))

## Installation

```bash
git clone https://github.com/youruser/claude-tg-bridge.git
cd claude-tg-bridge

# Copy and fill in your credentials
cp .env.example .env
# Edit .env with your TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID

# Install as CLI command
./install.sh
```

Files are installed to `~/.local/share/claude-tg-bridge/`. After install, `claude-tg` is available system-wide (requires `~/.local/bin` in your `PATH`).

## Usage

```bash
# Run from any project directory
cd ~/my-project
claude-tg

# Or specify a project path
claude-tg /path/to/project
```

This creates a tmux session named `claude-<project>` with two windows:

- **code** — Claude Code running in your project directory
- **bridge** — the Telegram bot listening for your messages

A startup notification is sent to Telegram as soon as the session is created.

The bridge window auto-stops when you detach from the tmux session (watchdog checks every 15 seconds).

## Configuration

`.env` file (placed next to `start.sh` or in the install directory):

| Variable | Description | Default |
|----------|-------------|---------|
| `TELEGRAM_BOT_TOKEN` | Bot token from @BotFather | *(required)* |
| `TELEGRAM_CHAT_ID` | Authorized Telegram chat ID | *(required)* |
| `TMUX_TARGET` | tmux pane target for Claude Code | set automatically by `start.sh` |

`TMUX_TARGET` is set automatically to `claude-<project>:code` by `start.sh`. You only need to set it manually if running `tg_bridge.py` directly.

### Setting up the response hook

To get Claude's responses back in Telegram, configure `send-to-telegram.sh` as a Claude Code hook. Add to your Claude Code settings (`~/.claude/settings.json`):

```json
{
  "hooks": {
    "Stop": [
      {
        "type": "command",
        "command": "~/.local/share/claude-tg-bridge/send-to-telegram.sh"
      }
    ],
    "Notification": [
      {
        "type": "command",
        "command": "~/.local/share/claude-tg-bridge/send-to-telegram.sh"
      }
    ],
    "StopFailure": [
      {
        "type": "command",
        "command": "~/.local/share/claude-tg-bridge/send-to-telegram.sh"
      }
    ]
  }
}
```

## How it works

1. `claude-tg` (`start.sh`) kills any existing `claude-*` tmux sessions (single-session policy), then creates a new session named `claude-<project>`
2. Window `code` runs Claude Code in your project directory
3. Window `bridge` runs `tg_bridge.py` — a Telegram bot that polls for messages
4. A startup notification is posted to Telegram via the Bot API
5. When you send a message in Telegram, the bot injects it into Claude Code's tmux pane via `tmux send-keys`
6. When Claude Code finishes, the `send-to-telegram.sh` hook fires and posts the response back to Telegram
7. A background watchdog thread in `tg_bridge.py` monitors tmux client connections and stops the bridge when you detach

## License

MIT
