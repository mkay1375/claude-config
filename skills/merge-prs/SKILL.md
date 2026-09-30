---
name: merge-prs
description: Squash-merge PRs on GitHub or MRs on GitLab, including self-hosted (the ones given, or your open ones) one by one, first reviewing with the built-in code review only those not yet reviewed at their head commit or that may clash with other PRs, and fixing critical issues on their branches.
argument-hint: [pr-number ...]
disable-model-invocation: true
---

PRs given: $ARGUMENTS

Running this command is the authorization to push fixes to these PR branches and merge them.
Do not stop to ask before merging.

## Git server

The commands below are for GitHub. Find the server from `origin`'s host: `gh auth status
--hostname <host>` succeeding means GitHub (including Enterprise), `glab auth status --hostname
<host>` means GitLab (including self-hosted, whose URL often doesn't say "gitlab"). If neither is
logged in, ask the user to log in and stop. On GitLab, "PR" means merge request and you use the
`glab` equivalents; tell subagents which server it is. Watch for:

- `glab mr merge` sets auto-merge by default; pass `--auto-merge=false` so it merges now, after
  the CI wait, and `--sha <head>` so only the reviewed commit is merged.
- Post the `Reviewed at` marker as a plain MR note through the API
  (`glab api -X POST "projects/:id/merge_requests/<n>/notes" -f body=...`); `glab mr note` is
  experimental.
- "Changes requested" is `detailed_merge_status == "requested_changes"` in `glab mr view -F json`.
- Run the built-in `code-review` on the checked-out MR branch, without an MR number.

## 0. Pick the PRs

- If PRs were given above, process those, in that order.
- Otherwise, list your open, non-draft PRs on GitHub that no other run has claimed with
  `gh pr list --state open --author @me --search '-label:reviewing -is:draft' --json number,title --jq 'sort_by(.number)'`
  and process them oldest first.
- If neither gives any PR, say so and stop.

## 1. Triage and claim

For each PR run
`gh pr view <n> --json number,title,state,isDraft,mergeable,reviewDecision,statusCheckRollup,headRefName,headRefOid,baseRefName,labels,files`.
Skip, and report why, any PR that is closed, a draft, has merge conflicts, has changes
requested, or already carries the `reviewing` label (another run has it).

Claim every PR that survives triage so a concurrent run leaves it alone: make sure the label
exists with `gh label create reviewing --color FBCA04 --description "A merge-prs run has this PR" --force`,
then `gh pr edit <n> --add-label reviewing`. From here on, every PR this run claimed must lose
the label before the run ends (step 5), whatever happens to it.

## 2. Decide which PRs need a review

A PR needs a review if either holds; record which, and for a clash, the files and PRs involved.

- **Not reviewed at its head.** A PR is reviewed when it has a comment whose first line is
  `Reviewed at <its current head SHA>` (the marker from the "Marking a PR reviewed" rule in
  `~/.claude/CLAUDE.md`). Check with
  `gh pr view <n> --json headRefOid,comments --jq '.headRefOid as $h | any(.comments[]; .body | startswith("Reviewed at " + $h))'`.
  A marker naming an older SHA does not count: commits came after the review.
- **May clash.** The PR changes a file that is also changed by
  - a PR earlier in this run's order (it will land on top of that one), or
  - its base branch since the PR branched off, listed with
    `gh api "repos/{owner}/{repo}/compare/<headRefOid>...<baseRefName>" --jq '.files[].filename'`.

PRs that need neither go straight to step 4.

## 3. Review and fix: one subagent per PR that needs it, in parallel

Launch one Agent per PR from step 2 in a single message, each with `isolation: "worktree"` so
they never share a checkout with each other or with other sessions. Tell each subagent why the
PR is being reviewed, and:

- Run `gh pr checkout <n>`, and read the PR description with `gh pr view <n>`.
- If the PR clashes with its base branch, first merge the base in (`git fetch origin` and
  `git merge origin/<baseRefName>`) so the review sees the code as it will land. If that
  conflicts, stop and report the PR as blocking.
- Run the built-in review through the Skill tool: `code-review` with args `<n> high --fix`.
- If the PR clashes with other PRs in this run, also read their diffs (`gh pr diff <other>`)
  and check the shared files for breakage once both land: a renamed or removed symbol the
  other uses, a changed signature or behaviour the other relies on, colliding migrations.
- Keep only the fixes for **critical** issues: correctness bugs, data loss, security holes,
  broken migrations, a failing build or failing tests, a break between clashing PRs. Revert
  every other change the review applied (style, simplification, nitpicks) with
  `git checkout -- <file>` or `git restore -p`.
- If a critical issue needs a design decision rather than an obvious fix, leave it unfixed and
  report it as blocking.
- Run the repo's checks if it has them (for a Makefile: `make format`, `make check`,
  `make test`) and fix only what the kept fixes broke.
- Commit with a message naming the issue fixed, and `git push` to the PR branch. Never
  force-push.
- Unless something is blocking, mark the PR reviewed: `gh pr comment <n> --body` with first
  line `Reviewed at <git rev-parse HEAD after the push>` and a second line
  `merge-prs: /code-review high --fix`.
- Report back: PR number, critical issues found, what was fixed (commit SHAs), what is
  blocking, and whether the checks pass.

## 4. Merge sequentially, in the order given

For each PR:

1. If it was reviewed in step 3, read the subagent's commits (`git show <sha>` or
   `gh pr diff <n>`). If a fix is wrong or goes beyond the critical issue, skip the PR and
   report it. Skip it too if anything is blocking or the checks failed.
2. Wait for CI: `gh pr checks <n> --watch`. Skip it if CI fails.
3. `gh pr merge <n> --squash --delete-branch`.
4. Before the next PR: if it now conflicts or is behind its base, run
   `gh pr update-branch <n>` and wait for CI again. Skip it if either fails.

## 5. Release the claims

For every PR this run labelled in step 1, merged or skipped, run
`gh pr edit <n> --remove-label reviewing`. Do this even when the run stops early; a label left
behind hides the PR from every later run until someone removes it by hand.

## 6. Report

A table: PR | reviewed this run (no: already reviewed / yes: unreviewed, clash with …) |
critical issues found | fixed | merged / skipped (reason).

## 7. Clean up leftover worktrees

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
Finish with `git worktree prune`. For a wider sweep of stale worktrees and branches, point the
user to `/cleanup`.
