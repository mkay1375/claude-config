#!/usr/bin/env bash
# SessionStart hook: report other non-idle Claude Code sessions whose working directory is this one.
# Stdout of a SessionStart hook is added to the new session's context.

dir="${CLAUDE_PROJECT_DIR:-$PWD}"

# This session's own claude process is one of our ancestors; skip every ancestor.
ancestors=" "
pid=$$
while [ -n "$pid" ] && [ "$pid" -gt 1 ]; do
  ancestors+="$pid "
  pid=$(ps -o ppid= -p "$pid" | tr -d ' ')
done

field_of() {
  jq -r ".$2 // empty" "$HOME/.claude/sessions/$1.json" 2>/dev/null
}

# Succeeds when the newest turn in the session's transcript is finished or interrupted, or when
# the session has no transcript because it never got a prompt. Slash commands the CLI answers
# itself (/model, /clear) are not turns. An unreadable or half-written transcript fails, so a
# session that is writing right now still counts as working.
turn_is_over() {
  local transcript
  transcript=$(ls "$HOME"/.claude/projects/*/"$1".jsonl 2>/dev/null | head -n 1)
  [ -n "$transcript" ] || return 0
  tail -r "$transcript" | jq -n -e '
    def local_command:
      (.message.content | type) == "string"
      and (.message.content | test("^<(local-command-|command-name>)"));
    def interrupted:
      (.message.content | type) == "array"
      and ((.message.content[0].text // "") | startswith("[Request interrupted by user"));
    [limit(1; inputs
      | select(.isSidechain != true and .isMeta != true)
      | select(.type == "assistant" or (.type == "user" and (local_command | not))))][0]
    | . == null
      or (.type == "assistant" and .message.stop_reason == "end_turn")
      or (.type == "user" and interrupted)
  ' >/dev/null 2>&1
}

# A dialog such as /usage reports "waiting" whether it was opened at rest or in the middle of a
# turn, and paused-session prompts report the same "dialog open", so only the transcript tells a
# session that is merely showing a dialog from one that still has work in flight.
showing_a_dialog_at_rest() {
  [ "$(field_of "$1" status)" = "waiting" ] || return 1
  [ "$(field_of "$1" waitingFor)" = "dialog open" ] || return 1
  turn_is_over "$(field_of "$1" sessionId)"
}

others=()
while read -r pid comm; do
  [[ "$comm" =~ (^|/)claude$ ]] || continue
  [[ "$ancestors" == *" $pid "* ]] && continue
  cwd=$(lsof -a -p "$pid" -d cwd -Fn 2>/dev/null | sed -n 's/^n//p')
  [ "$cwd" = "$dir" ] || continue
  # Claude Code keeps each session's state (idle/busy/waiting) in ~/.claude/sessions/<pid>.json.
  # A missing or unreadable file counts as active, so an unknown session still warns.
  status=$(field_of "$pid" status)
  [ "$status" = "idle" ] && continue
  showing_a_dialog_at_rest "$pid" && continue
  others+=("$pid${status:+ ($status)}")
done < <(ps -Ao pid=,comm=)

[ ${#others[@]} -eq 0 ] && exit 0

list=$(printf ', %s' "${others[@]}")
echo "WARNING: ${#others[@]} other active Claude Code session(s) in $dir (pid: ${list:2})."
cat <<'EOF'
Before editing anything:
- If the current task depends on another session's task being finished, wait for that session
  to finish, then start working.
- Otherwise, ask the user whether to do the work in a new git worktree before creating one. If
  they agree, do the work there (never in the shared checkout): create the worktree on a new
  branch, do the job, commit, push, open a PR, and give the user the PR link.
EOF
