# Question notifications

Install `question-notify.py` under `~/.codex/hooks/` and **append** the
`PreToolUse` group in `question-notifications.json` to `~/.codex/hooks.json`.
Keep existing groups, including RTK's `Bash` hook and `SessionStart`.
For a custom Codex home, the installer must substitute that home in both
command paths. The script uses only Python 3's standard library.

Restart Codex and run `/hooks` in the CLI to inspect and trust the new definition.
Do not write trust records or use a trust-bypass flag as part of installation.
Changing the definition requires another review. See the
[official hook trust flow](https://learn.chatgpt.com/docs/hooks#review-and-trust-hooks).

The notification contains the first nonempty `tool_input.questions[].question`
and the number of further questions. It accepts only `PreToolUse` for the exact
local names `request_user_input` and `request_user_input_async`; for an async
client that sends `tool_input.question`, it also accepts that single question.
Other tools, post-tool events, malformed inputs, and empty questions do nothing.

The [official hook coverage](https://learn.chatgpt.com/docs/hooks#tool-coverage)
documents local function-tool names and JSON arguments, but does not promise that
every specialized input tool uses that path. The synchronous question tool is
available only in modes/clients that expose it. Async tool availability and
schema depend on the client; an identically named function in the
[Responses API example](https://developers.openai.com/api/docs/guides/async-tool-calling)
is application-defined, not a promise of Codex support. This hook cannot enable
either tool. It also cannot detect prose questions, MCP elicitation, or cloud
orchestration that does not run local command hooks. Test a real question in the
client where you need notifications after trusting the hook.

On macOS the script uses `osascript`; on Linux it uses `notify-send` if available;
on Windows/Git Bash/WSL it uses Windows PowerShell when available. Messages are
passed as an argv value or environment variable, never inserted into executable
AppleScript, PowerShell, or shell text. Desktop permissions and platform tools
must permit notifications. Missing tools or notification errors are ignored.
The hook completes before the question tool runs, with a five-second command
timeout, and never returns a permission decision.

Validate parsing and command construction without sending a notification:

```sh
rtk proxy python3 -c 'import json; print(json.dumps({"hook_event_name":"PreToolUse","tool_name":"request_user_input","tool_input":{"questions":[{"question":"Which branch should I use?"}]}}))' |
  rtk proxy python3 codex/hooks/question-notify.py --dry-run --platform macos
rtk proxy python3 -m unittest discover -s codex/tests -p test_notifications.py
```
