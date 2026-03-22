#!/usr/bin/env python3
# ~/claude-tg-bridge/tg_bridge.py
#
# Listens to Telegram, injects messages into a tmux pane running Claude Code.
#
# /// script
# requires-python = ">=3.10"
# dependencies = ["python-telegram-bot==21.*"]
# ///

import asyncio
import logging
import os
import subprocess
import sys

from telegram import Update
from telegram.ext import Application, ContextTypes, MessageHandler, filters

# ─── Config (read from env) ───────────────────────────────────────────────────

BOT_TOKEN   = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID     = int(os.environ.get("TELEGRAM_CHAT_ID", "0"))
TMUX_TARGET = os.environ.get("TMUX_TARGET", "claude:code")   # session:window.pane

# ─── Logging ──────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# ─── Guards ───────────────────────────────────────────────────────────────────

if not BOT_TOKEN:
    sys.exit("❌  TELEGRAM_BOT_TOKEN is not set")
if CHAT_ID == 0:
    sys.exit("❌  TELEGRAM_CHAT_ID is not set")


# ─── Handler ──────────────────────────────────────────────────────────────────

async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Receive a message from Telegram and forward it to tmux."""
    chat = update.effective_chat
    user = update.effective_user
    text = update.message.text if update.message else None

    if not text:
        return

    # Only authorized chat
    if chat.id != CHAT_ID:
        log.warning("Rejected message from chat_id=%s (not authorized)", chat.id)
        return

    log.info("→ tmux  [%s]: %s", user.first_name if user else "?", text[:80])

    # Inject text into tmux as key presses
    try:
        subprocess.run(
            ["tmux", "send-keys", "-t", TMUX_TARGET, text, "Enter"],
            check=True,
            capture_output=True,
        )
        await update.message.reply_text("⏳ Sent to Claude…")
    except subprocess.CalledProcessError as e:
        err = e.stderr.decode().strip()
        log.error("tmux error: %s", err)
        await update.message.reply_text(
            f"❌ tmux error: `{err}`\n\nCheck that session `{TMUX_TARGET}` exists.",
            parse_mode="Markdown",
        )


# ─── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    log.info("[FIX] 🤖 Telegram→Claude bridge started (single-instance)")
    log.info("   tmux target : %s", TMUX_TARGET)
    log.info("   chat_id     : %s", CHAT_ID)
    log.info("   Only one bridge should be active at a time")

    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .build()
    )
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
