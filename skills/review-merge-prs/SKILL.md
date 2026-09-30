---
name: review-merge-prs
description: Review GitHub PRs (the ones given, or the open ones in .open-prs.txt) with the built-in code review, fix critical issues on each PR branch, and squash-merge them one by one.
argument-hint: [pr-number ...]
disable-model-invocation: true
---

PRs given: $ARGUMENTS

Running this command is the authorization to push fixes to these PR branches and merge them.
Do not stop to ask before merging.

## 0. Pick the PRs from `.open-prs.txt`

Sessions record the PRs they open in `.open-prs.txt` at the root of the main checkout
(`$(git rev-parse --path-format=absolute --git-common-dir)/..`), one `<pr-url> <status>` line
each, optionally followed by `# <comment>`. Status is `open` or `reviewing`.

- If PRs were given above, process those, in that order.
- Otherwise, if the file exists, process every line whose status is `open`, in file order. Skip
  `reviewing` lines: another review run has them.
- If neither gives any PR, say so and stop.

Before triage, set the status of every processed PR that has a line in the file to `reviewing`.
Other sessions append to this file while you work, so re-read it right before each write and
change only the lines for this run's PRs.

## 1. Triage

For each PR run
`gh pr view <n> --json number,title,state,isDraft,mergeable,reviewDecision,statusCheckRollup,headRefName`.
Skip, and report why, any PR that is closed, a draft, has merge conflicts, or has changes
requested.

## 2. Review and fix: one subagent per PR, in parallel

Launch one Agent per remaining PR in a single message, each with `isolation: "worktree"` so
they never share a checkout with each other or with other sessions. Tell each subagent:

- Run `gh pr checkout <n>`, and read the PR description with `gh pr view <n>`.
- Run the built-in review through the Skill tool: `code-review` with args `<n> high --fix`.
- Keep only the fixes for **critical** issues: correctness bugs, data loss, security holes,
  broken migrations, a failing build or failing tests. Revert every other change the review
  applied (style, simplification, nitpicks) with `git checkout -- <file>` or `git restore -p`.
- If a critical issue needs a design decision rather than an obvious fix, leave it unfixed and
  report it as blocking.
- Run the repo's checks if it has them (for a Makefile: `make format`, `make check`,
  `make test`) and fix only what the kept fixes broke.
- Commit with a message naming the issue fixed, and `git push` to the PR branch. Never
  force-push.
- Report back: PR number, critical issues found, what was fixed (commit SHAs), what is
  blocking, and whether the checks pass.

## 3. Merge sequentially, in the order given

For each PR:

1. Read the subagent's commits (`git show <sha>` or `gh pr diff <n>`). If a fix is wrong or
   goes beyond the critical issue, skip the PR and report it.
2. Skip it if anything is blocking or the checks failed.
3. Wait for CI: `gh pr checks <n> --watch`. Skip it if CI fails.
4. `gh pr merge <n> --squash --delete-branch`.
5. Before the next PR: if it now conflicts or is behind its base, run
   `gh pr update-branch <n>` and wait for CI again. Skip it if either fails.

## 4. Report

A table: PR | critical issues found | fixed | merged / skipped (reason).

## 5. Update `.open-prs.txt`

Re-read the file, then for each PR this run processed that has a line in it:

- Merged, by this run or before it: delete the line.
- Still open: set its status back to `open` and replace any old comment with
  `# <date>: <why it was not merged>`, e.g. `# 2026-09-30: CI failed on test_settle`.
- Closed without merging: delete the line and mention it in the report.

## 6. Clean up leftover worktrees

Subagent worktrees that ended with commits are not cleaned up automatically. After the report,
run `git worktree list` and pick out the worktrees this run's subagents left behind (each
subagent's result names its worktree path and branch). If there are none, stop.

Otherwise ask the user with AskUserQuestion (`multiSelect: true`) which ones to delete, one
option per worktree labelled with its PR number and whether that PR was merged or skipped. A
question takes at most four options, so split more than four worktrees across several questions.
Never delete without asking. This command authorizes merging, not deleting worktrees, and a
skipped PR's worktree may still hold work the user wants.

For each worktree the user picks, run `git worktree remove <path>` and then
`git branch -D <branch>` for its local branch. If `git worktree remove` refuses because of
uncommitted changes, report it and leave it; don't retry with `--force` unless the user says to.
Finish with `git worktree prune`.
