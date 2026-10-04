# Session folder checks

`other-sessions.sh` is the Claude Code hook. `other-sessions.py` is the Codex
`SessionStart` hook installed at `~/.codex/hooks/other-sessions.py`.

Codex CLI frontends and shared app servers can keep the directory where they
started while their chats work elsewhere. The Python hook checks the first
`session_meta` record of rollout files held open by live Codex processes. It
uses each chat's canonical `cwd`, includes chats sharing the current server,
and excludes the current session and its subagents using the hook's
`session_id` or `CODEX_THREAD_ID`. Guardian approval helpers are excluded too.
It reads no conversation records and never
scans historical rollout files for activity.

An open session does not establish that a turn is running: Codex warnings say
activity is unknown. Missing or unreadable metadata produces an incomplete
detection notice, without attributing the process's directory to its chats or
requiring a worktree on that evidence alone. Claude sessions continue to use
their process directory and existing idle-state checks.

The live rollout metadata format and process inspection are local runtime
details. If they change, the hook reports incomplete detection. The check is a
snapshot; recheck when another chat may have started since the scan. The hook
requires Python 3, `ps` and `lsof`.

Run the folder regression tests:

```sh
rtk proxy python3 -m unittest discover -s hooks/tests -p 'test_*.py'
```
