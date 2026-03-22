# claude-tg-bridge

Bidirectional bridge between Telegram and [Claude Code](https://docs.anthropic.com/en/docs/claude-code) running in a tmux session.

Send messages from Telegram — they get forwarded to Claude Code as input. Claude's responses are sent back to Telegram automatically.

## Features

- Forward Telegram messages to Claude Code via tmux keystroke injection
- Send Claude Code responses (Stop, Notification, StopFailure) back to Telegram
- Auto-create tmux session with Claude Code + bridge windows
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

After install, `claude-tg` is available system-wide (requires `~/.local/bin` in your `PATH`).

## Usage

```bash
# Source your env vars
source .env

# Run from any project directory
cd ~/my-project
claude-tg

# Or specify a project path
claude-tg /path/to/project
```

This creates a tmux session with two windows:
- **code** — Claude Code running in your project directory
- **bridge** — the Telegram bot listening for your messages

## Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `TELEGRAM_BOT_TOKEN` | Bot token from @BotFather | *(required)* |
| `TELEGRAM_CHAT_ID` | Authorized Telegram chat ID | *(required)* |
| `TMUX_TARGET` | tmux pane target for Claude Code | `claude:0` |

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
    ]
  }
}
```

## How it works

1. `claude-tg` (start.sh) creates a tmux session with Claude Code in window 0
2. A second tmux window runs `tg_bridge.py` — a Telegram bot that polls for messages
3. When you send a message in Telegram, the bot injects it into Claude Code's tmux pane via `tmux send-keys`
4. When Claude Code finishes, the `send-to-telegram.sh` hook fires and posts the response back to Telegram via the Bot API

## License

MIT
