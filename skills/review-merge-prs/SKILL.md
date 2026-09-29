---
name: review-merge-prs
description: Review a list of GitHub PRs with the built-in code review, fix critical issues on each PR branch, and squash-merge them one by one.
argument-hint: <pr-number> [pr-number ...]
disable-model-invocation: true
---

PRs to process: $ARGUMENTS

Running this command is the authorization to push fixes to these PR branches and merge them.
Do not stop to ask before merging.

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
