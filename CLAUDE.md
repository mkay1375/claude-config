@RTK.md

## Parallel sessions

A SessionStart hook (`~/.claude/hooks/other-sessions.sh`) warns when another Claude Code session
in the same directory is active (busy, or waiting on a prompt); idle sessions are skipped. When it
does, before editing anything:

- If the current task depends on the other session's task being finished, wait for that session
  to finish, then start working.
- Otherwise, ask the user whether to do the work in a new git worktree before creating one. If
  they agree, do the work there (never in the shared checkout): create the worktree on a new
  branch, do the job, commit, push, open a PR, and give the user the PR link.

## Large tasks

When a task is too big to do well in one pass, split it into parts and work through them one at
a time:

1. Run the part in a subagent.
2. Review what the subagent changed before accepting it.
3. Commit that part.
4. Move on to the next part and repeat.

Don't start the next part until the current one is reviewed and committed.
