#!/bin/bash
# ~/.claude/hooks/send-to-telegram.sh
# Fires on Stop and Notification events — sends Claude's message to Telegram

set -euo pipefail

INPUT=$(cat)
EVENT=$(echo "$INPUT" | jq -r '.hook_event_name')
MSG=$(echo "$INPUT" | jq -r '.last_assistant_message // .message // "..."')
CWD=$(echo "$INPUT" | jq -r '.cwd // ""')
PROJECT=$(basename "$CWD")

# Trim to Telegram's 4096-char limit, with a small buffer
MSG_TRIMMED=$(echo "$MSG" | head -c 3900)
if [ ${#MSG} -gt 3900 ]; then
  MSG_TRIMMED="${MSG_TRIMMED}… [trimmed]"
fi

# Choose icon by event type
case "$EVENT" in
  Stop)         ICON="✅" ;;
  Notification) ICON="🔔" ;;
  StopFailure)  ICON="❌" ;;
  *)            ICON="💬" ;;
esac

TEXT="${ICON} *${PROJECT}*
${MSG_TRIMMED}"

curl -s -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
  --data-urlencode "chat_id=${TELEGRAM_CHAT_ID}" \
  --data-urlencode "text=${TEXT}" \
  -d "parse_mode=Markdown" \
  > /dev/null
