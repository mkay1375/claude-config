---
name: review-merge-prs
description: Review GitHub PRs (the ones given, or your open ones on GitHub) with the built-in code review, fix critical issues on each PR branch, and squash-merge them one by one.
argument-hint: [pr-number ...]
disable-model-invocation: true
---

PRs given: $ARGUMENTS

Running this command is the authorization to push fixes to these PR branches and merge them.
Do not stop to ask before merging.

## 0. Pick the PRs

- If PRs were given above, process those, in that order.
- Otherwise, list your open, non-draft PRs on GitHub that no other run has claimed with
  `gh pr list --state open --author @me --search '-label:reviewing -is:draft' --json number,title --jq 'sort_by(.number)'`
  and process them oldest first.
- If neither gives any PR, say so and stop.

## 1. Triage and claim

For each PR run
`gh pr view <n> --json number,title,state,isDraft,mergeable,reviewDecision,statusCheckRollup,headRefName,labels`.
Skip, and report why, any PR that is closed, a draft, has merge conflicts, has changes
requested, or already carries the `reviewing` label (another review run has it).

Claim every PR that survives triage so a concurrent run leaves it alone: make sure the label
exists with `gh label create reviewing --color FBCA04 --description "A review-merge-prs run has this PR" --force`,
then `gh pr edit <n> --add-label reviewing`. From here on, every PR this run claimed must lose
the label before the run ends (step 4), whatever happens to it.

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

## 4. Release the claims

For every PR this run labelled in step 1, merged or skipped, run
`gh pr edit <n> --remove-label reviewing`. Do this even when the run stops early; a label left
behind hides the PR from every later run until someone removes it by hand.

## 5. Report

A table: PR | critical issues found | fixed | merged / skipped (reason).

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
