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
import hashlib
import logging
import os
import re
import signal
import subprocess
import sys
import threading
import time

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, ContextTypes, MessageHandler, filters

# ─── Config (read from env) ───────────────────────────────────────────────────

BOT_TOKEN   = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID     = int(os.environ.get("TELEGRAM_CHAT_ID", "0"))
TMUX_TARGET = os.environ.get("TMUX_TARGET", "claude:code")   # session:window.pane

# ─── Logging ──────────────────────────────────────────────────────────────────

LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# ─── Guards ───────────────────────────────────────────────────────────────────

if not BOT_TOKEN:
    sys.exit("❌  TELEGRAM_BOT_TOKEN is not set")
if CHAT_ID == 0:
    sys.exit("❌  TELEGRAM_CHAT_ID is not set")


# ─── Detection Engine ──────────────────────────────────────────────────────

ANSI_RE = re.compile(
    r'\x1b\[[0-9;?]*[A-Za-z@-~]'   # CSI sequences
    r'|\x1b\][^\x07]*\x07'          # OSC sequences
    r'|\x1b[()][A-Z0-9]'            # Character sets
    r'|\x1b[>=]'                     # Misc escapes
    r'|\r'                           # Carriage returns
)
PERMISSION_HEADER_RE = re.compile(r'Allow\s+(\w+)')
PERMISSION_OPTS_RE = re.compile(
    r'y\s+Allow.*?n\s+Deny'
    r'|\by\b.*\bn\b.*\ba\b.*allow',
    re.IGNORECASE,
)
OPTION_LINE_RE = re.compile(r'^\s*(\d+)[.)]\s+(.+)$', re.MULTILINE)

_last_prompt_hash: str = ""


def strip_ansi(text: str) -> str:
    """Remove ANSI escape sequences from text."""
    return ANSI_RE.sub('', text)


def capture_pane() -> str:
    """Capture current content of the tmux pane, stripped of ANSI codes."""
    log.debug("Capturing tmux pane: %s", TMUX_TARGET)
    try:
        result = subprocess.run(
            ["tmux", "capture-pane", "-p", "-t", TMUX_TARGET],
            capture_output=True, text=True, check=True,
        )
        cleaned = strip_ansi(result.stdout)
        log.debug("Captured %d chars from pane", len(cleaned))
        return cleaned
    except subprocess.CalledProcessError as e:
        log.debug("capture_pane failed: %s", e.stderr.strip() if e.stderr else e)
        return ""
    except FileNotFoundError:
        log.debug("tmux binary not found")
        return ""


def detect_prompt(pane_text: str) -> dict | None:
    """Detect permission or question prompts in pane content.

    Returns dict with type, text, options — or None.
    """
    global _last_prompt_hash

    if not pane_text.strip():
        return None

    lines = pane_text.rstrip().splitlines()
    tail = "\n".join(lines[-25:])

    # --- Permission prompt (y/n/a) ---
    header = PERMISSION_HEADER_RE.search(tail)
    opts = PERMISSION_OPTS_RE.search(tail)
    if header and opts:
        region = tail[header.start():opts.start()].strip()
        prompt_lines = []
        for line in region.splitlines():
            clean = line.strip().strip('│').strip()
            if clean and not all(c in '─╭╰╮╯ ' for c in clean):
                prompt_lines.append(clean)
        prompt_text = "\n".join(prompt_lines) if prompt_lines else header.group(0)

        prompt_hash = hashlib.md5(region.encode()).hexdigest()
        if prompt_hash == _last_prompt_hash:
            return None
        _last_prompt_hash = prompt_hash
        log.info("Detected permission prompt: %s", prompt_text.replace('\n', ' | '))
        return {
            "type": "permission",
            "text": prompt_text,
            "options": [
                ("✅ Allow", "y"),
                ("❌ Deny", "n"),
                ("🔓 Always", "a"),
            ],
        }

    # --- Question prompt (numbered options) ---
    option_matches = OPTION_LINE_RE.findall(tail)
    if len(option_matches) >= 2:
        question = "Choose an option:"
        for line in reversed(lines[-25:]):
            clean = line.strip().strip('│').strip()
            if (clean and len(clean) > 3
                    and not OPTION_LINE_RE.match(clean)
                    and not all(c in '─╭╰╮╯ ' for c in clean)):
                question = clean
                break

        opts_list = [(f"{num}. {text.strip()}", num) for num, text in option_matches]
        prompt_hash = hashlib.md5(
            (question + "|".join(n for n, _ in option_matches)).encode()
        ).hexdigest()
        if prompt_hash == _last_prompt_hash:
            return None
        _last_prompt_hash = prompt_hash
        log.info("Detected question prompt: %s (%d options)", question, len(opts_list))
        return {
            "type": "question",
            "text": question,
            "options": opts_list,
        }

    return None


# ─── Watchdog ─────────────────────────────────────────────────────────────

WATCHDOG_INTERVAL = 15  # seconds

def _tmux_watchdog() -> None:
    """Background thread: stop the bot when no clients are attached to the tmux session."""
    session = TMUX_TARGET.split(":")[0]
    while True:
        time.sleep(WATCHDOG_INTERVAL)
        try:
            result = subprocess.run(
                ["tmux", "list-clients", "-t", session],
                capture_output=True, text=True,
            )
            # Session gone (non-zero exit) or no clients attached (empty output)
            if result.returncode != 0 or not result.stdout.strip():
                log.warning("[FIX] No clients attached to '%s' — stopping bridge", session)
                os.kill(os.getpid(), signal.SIGINT)
                return
        except FileNotFoundError:
            log.warning("[FIX] tmux not found — stopping bridge")
            os.kill(os.getpid(), signal.SIGINT)
            return


# ─── Telegram Prompt UI ────────────────────────────────────────────────────

async def send_prompt_to_telegram(app: Application, prompt: dict) -> None:
    """Send a detected prompt to Telegram with inline keyboard buttons."""
    buttons = []
    for label, value in prompt["options"]:
        cb_data = f"perm:{value}" if prompt["type"] == "permission" else f"opt:{value}"
        buttons.append(InlineKeyboardButton(label, callback_data=cb_data))

    if prompt["type"] == "permission":
        keyboard = InlineKeyboardMarkup([buttons])
    else:
        keyboard = InlineKeyboardMarkup([[b] for b in buttons])

    await app.bot.send_message(
        chat_id=CHAT_ID,
        text=f"🔔 {prompt['text']}",
        reply_markup=keyboard,
    )
    log.info("Sent prompt buttons to Telegram: %s", prompt["text"].replace('\n', ' | '))


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle inline keyboard button presses — send keystroke to tmux."""
    query = update.callback_query
    if not query or not query.data:
        return

    if update.effective_chat.id != CHAT_ID:
        log.warning("Rejected callback from chat_id=%s", update.effective_chat.id)
        await query.answer("Unauthorized")
        return

    parts = query.data.split(":", 1)
    if len(parts) != 2:
        await query.answer("Invalid")
        return

    kind, value = parts
    log.debug("Callback received: kind=%s value=%s", kind, value)

    try:
        if kind == "perm":
            subprocess.run(
                ["tmux", "send-keys", "-t", TMUX_TARGET, value],
                check=True, capture_output=True,
            )
        elif kind == "opt":
            subprocess.run(
                ["tmux", "send-keys", "-t", TMUX_TARGET, value, "Enter"],
                check=True, capture_output=True,
            )

        log.info("Button → tmux: '%s'", value)
        await query.answer(f"Sent: {value}")
        await query.edit_message_reply_markup(reply_markup=None)
    except subprocess.CalledProcessError as e:
        err = e.stderr.decode().strip()
        log.error("tmux send-keys failed: %s", err)
        await query.answer(f"Error: {err}", show_alert=True)


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


# ─── Pane Monitor ──────────────────────────────────────────────────────────

POLL_INTERVAL = 1.5  # seconds


async def monitor_pane(app: Application) -> None:
    """Poll tmux pane for prompts and send buttons to Telegram."""
    log.info("Pane monitor started (polling every %.1fs)", POLL_INTERVAL)
    try:
        while True:
            await asyncio.sleep(POLL_INTERVAL)
            pane_text = capture_pane()
            if not pane_text:
                continue
            prompt = detect_prompt(pane_text)
            if prompt:
                await send_prompt_to_telegram(app, prompt)
    except asyncio.CancelledError:
        log.info("Pane monitor stopped")


async def post_init(app: Application) -> None:
    """Start the pane monitor after the application initializes."""
    asyncio.create_task(monitor_pane(app), name="pane_monitor")
    log.info("Pane monitor task created")


# ─── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    log.info("[FIX] 🤖 Telegram→Claude bridge started (single-instance)")
    log.info("   tmux target : %s", TMUX_TARGET)
    log.info("   chat_id     : %s", CHAT_ID)
    log.info("   Only one bridge should be active at a time")

    # Start watchdog: shuts down the bot if the tmux session disappears
    watchdog = threading.Thread(target=_tmux_watchdog, daemon=True)
    watchdog.start()
    log.info("[FIX] tmux watchdog started (checks every %ds)", WATCHDOG_INTERVAL)

    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .build()
    )
    app.add_handler(CallbackQueryHandler(on_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
