# claude-config

My user-level [Claude Code](https://claude.com/claude-code) configuration: the contents of
`~/.claude` that are worth carrying between machines.

| Path | What it is |
| --- | --- |
| `CLAUDE.md` | Global instructions loaded into every session |
| `RTK.md` | Notes on [RTK](https://github.com/rtk-ai/rtk), the token-saving CLI proxy, included by `CLAUDE.md` |
| `settings.json` | Model and effort, hooks, enabled plugins and marketplaces, theme, notifications |
| `hooks/other-sessions.sh` | `SessionStart` hook that warns when another busy Claude Code session shares the working directory |
| `skills/review-merge-prs/` | `/review-merge-prs <n>...`: reviews each PR in its own worktree subagent, fixes critical issues, squash-merges them in order |

## What is not tracked

`.gitignore` is an allow-list: everything is ignored unless named there. Claude Code writes
history, session transcripts, caches, telemetry and file history into `~/.claude`, and none of it
belongs here. Plugins reinstall from `settings.json`, and synced skills come from the claude.ai
account. To track a new file, add a `!/path` line to `.gitignore`.

## Setting up a new machine

```bash
git clone https://github.com/mkay1375/claude-config.git /tmp/claude-config
mkdir -p ~/.claude
mv /tmp/claude-config/.git ~/.claude/
cd ~/.claude && git checkout -- .
```

This clones into an existing `~/.claude` without touching the untracked files already there.

The hooks need `rtk` and `jq` on the `PATH`.
