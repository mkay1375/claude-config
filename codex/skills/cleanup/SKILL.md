---
name: cleanup
description: Clean up a git repo by deleting stale worktrees, local branches and remote branches (merged, squash-merged, closed or long inactive), on GitHub, GitLab (including self-hosted) or any other git server, after asking which to delete.
---

Read the repository path and options from the user's request:

- **repo path**: the repo to clean. Default: the repo containing the current directory.
- **--days N**: a branch or worktree with no commit in N days counts as inactive. Default 90.
- **--dry-run**: build and show the plan, delete nothing.
- **--local-only** / **--remote-only**: limit the run to worktrees plus local branches, or to
  remote branches.
- **--all-authors**: also offer remote branches whose tip commit someone else authored. By
  default only your own remote branches are candidates.

Deleting is hard to undo and deleting remote branches affects everyone. Running this command
authorizes finding candidates, not deleting them: always show the plan and ask (step 5) before
deleting anything.

## 1. Find the repo and its git server

1. `git -C <repo path> rev-parse --show-toplevel` gives the repo root; run everything below from
   there. If it is not a git repo, say so and stop. Use `git worktree list --porcelain` to find the
   main worktree (the first entry) and use it as the root, so the run works the same when started
   from inside a linked worktree.
2. Pick the remote: the one the default branch tracks, else `origin`, else the only remote. With no
   remote, skip everything remote and say so.
3. Pick the tool for the remote's host: `gh` if `gh auth status --hostname <host>` succeeds
   (GitHub, including Enterprise), else `glab` if `glab auth status --hostname <host>` succeeds
   (GitLab, including self-hosted, whose URL often doesn't say "gitlab"). Otherwise use plain git:
   the run still works on any server but cannot see PR/MR state or protected branches; if the host
   looks like GitHub or GitLab, suggest logging in with that CLI.
4. `git fetch --prune <remote>` so remote-tracking branches match the server.
5. The default branch: `git symbolic-ref --short refs/remotes/<remote>/HEAD` (strip the remote
   prefix). If that is unset, run `git remote set-head <remote> --auto` and try again; failing
   that, use `main` or `master`, whichever exists. `<default>` below is `<remote>/<default branch>`.

## 2. Gather what the server knows (GitHub / GitLab only)

Fetch once, in bulk rather than per branch, with JSON output: your login; open, merged and
closed-unmerged PRs/MRs with their head branch, number, author and dates; and the protected
branches. Page through all results; list commands cap how many they return by default.

Protected-branch entries can be wildcards (`release/*`); treat them as globs. If a call fails for
lack of permission, carry on without it and say which data is missing. A branch name can have had
several PRs/MRs; the most recent one decides its state.

## 3. Classify candidates

**Never a candidate**, whatever else holds: the default branch, the branch checked out in the main
worktree, the branch checked out where this session is running, protected branches, `HEAD`, any
branch with an open PR/MR, and any branch checked out in a worktree that is being kept.

A branch is **merged** when any of these holds:
- `git merge-base --is-ancestor <branch> <default>` succeeds (merge or fast-forward);
- its PR/MR is merged and the branch tip is the PR/MR head or older (no commits pushed after
  the merge);
- plain-git squash check: `git cherry <default> "$(git commit-tree "$(git rev-parse <branch>^{tree})" -p "$(git merge-base <default> <branch>)" -m _)"`
  prints a line starting with `-` (the branch's whole diff is already in the default branch).

### Worktrees

From `git worktree list --porcelain`, skip the main worktree and the one this session runs in.
For each other worktree record: path, branch (or detached SHA), last commit date, and:
- **dirty**: `git -C <path> status --porcelain` prints anything;
- **unpushed**: commits not on any remote branch
  (`git -C <path> log --oneline HEAD --not --remotes`);
- **locked** (`locked` line in the porcelain output) or **prunable** (directory gone);
- **in use**: the worktree's index or a file near its top changed in the last hour
  (`find "$(git -C <path> rev-parse --path-format=absolute --git-path index)" <path> -maxdepth 3 -mmin -60 -not -path '*/node_modules/*' -print -quit`
  prints anything), which usually means another session is working there.

Categories:
- **Gone**: prunable. Removed by `git worktree prune`, no data at risk.
- **Merged**: its branch is merged (or detached at a commit already in `<default>`), clean,
  with no unpushed commits, not locked, not in use.
- **Inactive**: last commit older than `--days`, clean, with no unpushed commits, not locked,
  not in use.
- **Needs a look**: anything else that is merged or inactive but dirty, unpushed, locked or in use.
  Offered only on its own, never grouped with the safe ones.

### Local branches

From `git for-each-ref refs/heads --format='%(refname:short)|%(upstream:short)|%(upstream:track)|%(committerdate:iso-strict)|%(objectname:short)'`,
excluding the never-candidates and branches used by kept worktrees:
- **Merged**.
- **Upstream gone and PR/MR merged**: upstream shows `[gone]` and the squash check or server state
  says merged.
- **Closed unmerged**: its PR/MR was closed without merging.
- **Upstream gone, not merged**: upstream `[gone]` but no evidence it was merged; the work may
  exist only here. Put it under "needs a look".
- **Inactive**: no upstream or not merged, last commit older than `--days`, with the count of
  commits not in `<default>` (`git rev-list --count <default>..<branch>`).

A branch whose worktree is removed in this run is judged with that worktree.

### Remote branches

From `git for-each-ref refs/remotes/<remote> --format='%(refname:lstrip=3)|%(committerdate:iso-strict)|%(authoremail)|%(authorname)|%(objectname:short)'`,
excluding the never-candidates:
- **Merged**, **closed unmerged** and **inactive** as for local branches.
- Unless `--all-authors` was given, keep only branches whose tip author email matches
  `git config user.email` or whose PR/MR author is your login. Say how many other people's stale
  branches were left out, so the user can rerun with `--all-authors`.

## 4. Show the plan

Print one table per kind (worktrees, local branches, remote branches), each row numbered:
`# | name / path | category | last commit (date, age) | PR/MR (number, state) | notes` where
notes carry dirty, unpushed, locked, in use, commits ahead, author. Order rows by category, safe
first. End with totals per category. If there is nothing to clean, say so and stop.

With `--dry-run`, stop here.

## 5. Ask

Ask the user in chat to approve specific row numbers or named groups from the plan, for
example "Local: merged (12)" or "Remote: closed unmerged (3)". State which data each selection
would delete. Keep "needs a look" items individually selectable and explain their dirty,
unpushed, locked or active status. Wait for their answer; no reply is not approval. A Codex
question tool that disallows permission requests is not suitable for this deletion approval.
Follow row additions and exclusions exactly. Delete nothing that was not chosen.

If the user has already approved a concrete plan in this session, use that authorization rather
than asking again; candidate discovery alone is not a concrete deletion plan.

## 6. Delete, in this order

Recheck every selected item's tip, worktree status, protection and open-request state against
the approved plan immediately before deleting. If its tip or risk changed, skip it and report
why. Never delete newly discovered items under an earlier approval.

Before deleting, print every branch and worktree about to go with its tip SHA, so any of them can
be restored later with `git branch <name> <sha>` or `git push <remote> <sha>:refs/heads/<name>`.

1. **Worktrees**: `git worktree prune` for the gone ones, then `git worktree remove <path>` for
   each chosen one. If it refuses (dirty, locked), report it and move on. Use `--force` only for a
   worktree the user explicitly chose from "needs a look" knowing it is dirty; never
   `--force --force` for a locked one unless the user says so.
2. **Local branches**: `git branch -d <branch>` for ones git sees as merged; `git branch -D <branch>`
   for the chosen squash-merged, closed or inactive ones (git cannot see those as merged).
3. **Remote branches**: delete each selected branch conditionally at its approved tip:
   `git push --force-with-lease=refs/heads/<branch>:<approved-sha> <remote> :refs/heads/<branch>`.
   This prevents deleting commits pushed after the plan was approved. If the server rejects
   one (changed tip, protected, no permission), report it and go on; never retry without the lease.
   A branch that was already gone on the server is fine; drop it from the report's error list.

If a step fails for one item, keep going with the rest; never retry a refused deletion with a
stronger flag on your own.

## 7. Report

A short table per kind: deleted, skipped (why), failed (error). Then the restore list
(name → SHA) for everything deleted, and one line with what is left that the user may want to look
at by hand (for example dirty worktrees or other people's branches left out).
