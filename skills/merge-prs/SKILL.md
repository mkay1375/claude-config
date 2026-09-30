---
name: merge-prs
description: Squash-merge PRs on GitHub or MRs on GitLab, including self-hosted GitLab (the ones given, or your open ones), one by one, first reviewing with the built-in code review only those not yet reviewed at their head commit or that may clash with others, and fixing critical issues on their branches.
argument-hint: [pr-number ...]
disable-model-invocation: true
---

PRs given: $ARGUMENTS

Running this command is the authorization to push fixes to these PR branches and merge them.
Do not stop to ask before merging.

"PR" below also means a GitLab merge request (MR); its number is the MR's `iid` (the `!123`).

## Which git server

Take the host from `git remote get-url origin` (`git@host:path`, `ssh://git@host:port/path` or
`https://host/path`):

- `gh auth status --hostname <host>` succeeds (github.com or GitHub Enterprise) → **GitHub**:
  use the GitHub column of the table below.
- Else `glab auth status --hostname <host>` succeeds (gitlab.com or a self-hosted GitLab) →
  **GitLab**: use the GitLab column. `glab` finds the host from the git remote on its own.
- Else stop and tell the user to log in with `gh auth login --hostname <host>` or
  `glab auth login --hostname <host>`. Other servers have no PRs this command can drive.

Every step names its action in **bold**; this table gives the command for it. In GitLab API paths
`:id` is filled in by `glab` with the current project; a branch name in a query string must be
URL-encoded (`/` → `%2F`). Tell subagents which column to use.

| Action | GitHub | GitLab |
| --- | --- | --- |
| **list mine** | `gh pr list --state open --author @me --search '-label:reviewing -is:draft' --json number,title --jq 'sort_by(.number)'` | `glab mr list --author "$(glab api user \| jq -r .username)" --not-draft --not-label reviewing -P 100 -F json --jq 'sort_by(.iid) \| .[] \| {iid, title}'` |
| **view** | `gh pr view <n> --json number,title,state,isDraft,mergeable,reviewDecision,statusCheckRollup,headRefName,headRefOid,baseRefName,labels,files` | `glab mr view <n> -F json`: fields `state`, `draft`, `has_conflicts`, `detailed_merge_status`, `source_branch`, `sha`, `target_branch`, `labels`, `head_pipeline` |
| head SHA / head branch / base branch | `headRefOid` / `headRefName` / `baseRefName` | `sha` / `source_branch` / `target_branch` |
| closed, draft, conflicts, changes requested | `state != "OPEN"`, `isDraft`, `mergeable == "CONFLICTING"`, `reviewDecision == "CHANGES_REQUESTED"` | `state != "opened"`, `draft`, `has_conflicts`, `detailed_merge_status == "requested_changes"` |
| **ensure label** | `gh label create reviewing --color FBCA04 --description "A merge-prs run has this PR" --force` | `glab label create --name reviewing --color '#FBCA04' --description "A merge-prs run has this MR"` (an "already exists" error is fine) |
| **add label** / **remove label** | `gh pr edit <n> --add-label reviewing` / `--remove-label reviewing` | `glab mr update <n> --label reviewing --yes` / `--unlabel reviewing --yes` |
| **reviewed?** | `gh pr view <n> --json headRefOid,comments --jq '.headRefOid as $h \| any(.comments[]; .body \| startswith("Reviewed at " + $h))'` → `true` | `glab api --paginate "projects/:id/merge_requests/<n>/notes?per_page=100" \| jq -r '.[] \| select(.body \| startswith("Reviewed at <head SHA>")) \| .id'` → prints an id |
| **files changed** | `gh pr view <n> --json files --jq '.files[].path'` | `glab api --paginate "projects/:id/merge_requests/<n>/diffs?per_page=100" \| jq -r '.[] \| .new_path, .old_path' \| sort -u` |
| **base changes** (files changed on the base since the PR branched off) | `gh api "repos/{owner}/{repo}/compare/<head SHA>...<base branch>" --jq '.files[].filename'` | `glab api "projects/:id/repository/compare?from=<head SHA>&to=<base branch>" \| jq -r '.diffs[] \| .new_path, .old_path' \| sort -u` |
| **checkout** | `gh pr checkout <n>` | `glab mr checkout <n>` |
| **read description** | `gh pr view <n>` | `glab mr view <n>` |
| **diff** | `gh pr diff <n>` | `glab mr diff <n>` |
| **comment** | `gh pr comment <n> --body "<text>"` | `glab api -X POST "projects/:id/merge_requests/<n>/notes" -f body="<text>"` |
| **wait for CI** | `gh pr checks <n> --watch`; fails if any check fails | `glab ci status --branch <head branch> --wait`, then `glab mr view <n> -F json --jq '.head_pipeline.status'` must be `success` (`null` means the project has no CI) |
| **merge** | `gh pr merge <n> --squash --delete-branch` | `glab mr merge <n> --squash --remove-source-branch --sha <head SHA> --auto-merge=false --yes` |
| **update branch** | `gh pr update-branch <n>` | `glab mr rebase <n>` |
| **code review args** | `<n> high --fix` | `high --fix` (on the checked-out MR branch) |

## 0. Pick the PRs

- If PRs were given above, process those, in that order.
- Otherwise, **list mine**: your open, non-draft PRs that no other run has claimed, and process
  them oldest first.
- If neither gives any PR, say so and stop.

## 1. Triage and claim

For each PR, **view** it. Skip, and report why, any PR that is closed, a draft, has merge
conflicts, has changes requested, or already carries the `reviewing` label (another run has it).

Claim every PR that survives triage so a concurrent run leaves it alone: **ensure label**, then
**add label**. From here on, every PR this run claimed must lose the label before the run ends
(step 5), whatever happens to it.

## 2. Decide which PRs need a review

A PR needs a review if either holds; record which, and for a clash, the files and PRs involved.

- **Not reviewed at its head.** A PR is reviewed when it has a comment whose first line is
  `Reviewed at <its current head SHA>` (the marker from the "Marking a PR reviewed" rule in
  `~/.claude/CLAUDE.md`). Check with **reviewed?**. A marker naming an older SHA does not count:
  commits came after the review.
- **May clash.** The PR changes a file (**files changed**) that is also changed by
  - a PR earlier in this run's order (it will land on top of that one), or
  - its base branch since the PR branched off (**base changes**).

PRs that need neither go straight to step 4.

## 3. Review and fix: one subagent per PR that needs it, in parallel

Launch one Agent per PR from step 2 in a single message, each with `isolation: "worktree"` so
they never share a checkout with each other or with other sessions. Tell each subagent why the
PR is being reviewed, which git server it is on with the commands it needs from the table, and:

- **Checkout** the PR, and **read description**.
- If the PR clashes with its base branch, first merge the base in (`git fetch origin` and
  `git merge origin/<base branch>`) so the review sees the code as it will land. If that
  conflicts, stop and report the PR as blocking.
- Run the built-in review through the Skill tool: `code-review` with the **code review args**.
- If the PR clashes with other PRs in this run, also read their **diff** and check the shared
  files for breakage once both land: a renamed or removed symbol the other uses, a changed
  signature or behaviour the other relies on, colliding migrations.
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
- Unless something is blocking, mark the PR reviewed: **comment** with first line
  `Reviewed at <git rev-parse HEAD after the push>` and a second line
  `merge-prs: /code-review high --fix`.
- Report back: PR number, critical issues found, what was fixed (commit SHAs), what is
  blocking, and whether the checks pass.

## 4. Merge sequentially, in the order given

For each PR:

1. If it was reviewed in step 3, read the subagent's commits (`git show <sha>` or the PR's
   **diff**). If a fix is wrong or goes beyond the critical issue, skip the PR and report it.
   Skip it too if anything is blocking or the checks failed.
2. **Wait for CI**. Skip it if CI fails.
3. **Merge**, with the head SHA from a fresh **view**.
4. Before the next PR: if it now conflicts or is behind its base, **update branch** and wait for
   CI again. Skip it if either fails.

## 5. Release the claims

For every PR this run labelled in step 1, merged or skipped, **remove label**. Do this even when
the run stops early; a label left behind hides the PR from every later run until someone
removes it by hand.

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
