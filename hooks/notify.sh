#!/usr/bin/env bash
# Desktop notification for Claude Code hooks, on macOS, Windows (Git Bash), WSL and Linux.
# Usage: notify.sh [default message]   (hook JSON on stdin; its "message" field wins if present)

msg="${1:-Claude needs you}"

# All values of a JSON string field, one per line, unescaped (no jq, so it works in Git Bash).
json_values() {
  printf '%s' "$input" \
    | grep -oE "\"$1\"[[:space:]]*:[[:space:]]*\"([^\"\\\\]|\\\\.)*\"" \
    | sed -E "s/^\"$1\"[[:space:]]*:[[:space:]]*\"//; s/\"\$//; s/\\\\n/ /g; s/\\\\\"/\"/g; s/\\\\\\\\/\\\\/g"
}

if [ ! -t 0 ]; then
  input=$(cat)
  questions=$(json_values question)   # AskUserQuestion: tool_input.questions[].question
  if [ -n "$questions" ]; then
    msg=$(printf '%s\n' "$questions" | head -n1)
    count=$(printf '%s\n' "$questions" | wc -l | tr -d ' ')
    [ "$count" -gt 1 ] && msg="$msg (+$((count - 1)) more)"
  else
    from_json=$(json_values message | head -n1)   # Notification event
    [ -n "$from_json" ] && msg="$from_json"
  fi
fi

# Windows toast via Windows PowerShell 5.1; message passed by env var to avoid quoting issues.
windows_toast() {
  export CLAUDE_NOTIFY_MSG="$msg"
  export WSLENV="${WSLENV:+$WSLENV:}CLAUDE_NOTIFY_MSG/u"
  powershell.exe -NoProfile -NonInteractive -Command '
    [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
    $x = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
    $t = $x.GetElementsByTagName("text")
    $t.Item(0).AppendChild($x.CreateTextNode("Claude Code")) | Out-Null
    $t.Item(1).AppendChild($x.CreateTextNode($env:CLAUDE_NOTIFY_MSG)) | Out-Null
    $app = "{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe"
    [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($app).Show([Windows.UI.Notifications.ToastNotification]::new($x))
  ' >/dev/null 2>&1
}

case "$(uname -s)" in
  Darwin)
    osascript -e 'on run argv' \
      -e 'display notification (item 1 of argv) with title "Claude Code" sound name "Glass"' \
      -e 'end run' "$msg" >/dev/null 2>&1
    ;;
  MINGW*|MSYS*|CYGWIN*)
    windows_toast &
    ;;
  Linux)
    if grep -qi microsoft /proc/version 2>/dev/null && command -v powershell.exe >/dev/null; then
      windows_toast &
    elif command -v notify-send >/dev/null; then
      notify-send "Claude Code" "$msg"
    else
      printf '\a' >/dev/tty 2>/dev/null
    fi
    ;;
esac
exit 0
