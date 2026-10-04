---
name: merge-prs
description: Review and squash-merge selected GitHub PRs or GitLab MRs, including self-hosted, in order. Reuse current-head review evidence from descriptions or comments, review overlaps, fix critical issues in isolated worktrees, and wait for CI.
---

Read PR/MR numbers from the user's request and preserve their order. With no numbers, select
the user's open, non-draft requests, oldest first. Explicitly invoking this skill authorizes
pushing critical fixes to the selected branches and merging those requests; do not ask again
before merging. It does not authorize deleting leftover local worktrees or local branches.

## Git server

Identify the repository and `origin` host. Use `gh auth status --hostname <host>` for GitHub
(including Enterprise), or `glab auth status --hostname <host>` for GitLab (including
self-hosted). A self-hosted GitLab URL need not contain "gitlab". Pass the selected repository
and host explicitly when CLI defaults might target another repository. If neither CLI is
authenticated for the host, ask the user to log in and stop.

Examples below use GitHub. On GitLab, use equivalent MR APIs and commands, and tell each
worker the host, repository and request type. In particular:

- Use `glab mr merge <n> --squash --auto-merge=false --sha <reviewed-head> --yes`
  after pipelines succeed.
- Post the review marker as a plain MR note through
  `glab api -X POST "projects/:id/merge_requests/<n>/notes" -f body=<text>`.
- Treat `detailed_merge_status == "requested_changes"` as changes requested.
- Review the checked-out MR against its fetched target branch using the same Codex workflow.

## 0. Pick requests

If numbers were supplied, use those in order. Otherwise use:

```bash
gh pr list --state open --author @me --search '-label:reviewing -is:draft' --json number,title --jq 'sort_by(.number)'
```

Paginate if necessary so the default CLI limit does not silently omit requests. On GitLab,
list the authenticated user's open, non-draft MRs without the `reviewing` label and sort by
creation time. If none qualify, report that and stop.

## 1. Triage and claim

For each PR read:

```bash
gh pr view <n> --json number,title,body,state,isDraft,mergeable,reviewDecision,statusCheckRollup,headRefName,headRefOid,baseRefName,labels,files,comments
```

Read the description before deciding whether another review is needed. It can contain completed
review evidence as well as the request's intent, validation and known limitations. On GitLab,
fetch `description`, `sha`, changed files and all MR notes with the corresponding fields.

Skip closed requests, drafts, merge conflicts, changes requested and requests already labelled
`reviewing`. If mergeability is still being computed, refresh it before deciding; report
unresolved state rather than assuming the request is mergeable.

Ensure a `reviewing` label exists without overwriting its existing metadata. Recheck the
request before adding it with `gh pr edit <n> --add-label reviewing`. This label is an advisory
claim, not an atomic lock; avoid concurrent runs on the same requests. Record every claim this
run added, and release it in step 5 even if the run fails or is interrupted.

## 2. Decide which requests need review

A request needs review if either condition holds:

- **No review at its current head.** Accept either a comment's exact first line or an exact
  standalone line in the request description: `Reviewed at <current head SHA>`. The description
  marker must start the body or follow a blank line, outside quotes, code and HTML blocks.
  This boundary avoids treating lazy quote/list continuations as completed reviews. The SHA
  must be the full current 40-character head. A description can record review evidence like this:

  ```text
  Reviewed at 0123456789abcdef0123456789abcdef01234567
  Codex review against origin/main; critical fixes verified
  ```

  This example is a template, not evidence for another SHA. Vague claims such as "reviewed",
  abbreviated or older SHAs, blockquotes, fenced examples and HTML examples/comments do not
  certify the current head. Put a blank line between a review heading and the actual marker.
  Existing descriptions without a full-head marker need review once; when completing that
  review, post the standard comment marker below so later runs can reuse it.

  Save fresh GitHub request JSON and check it with this skill's helper:

  ```bash
  gh pr view <n> --json headRefOid,body,comments > <request-json>
  python3 <skill-dir>/scripts/review_evidence.py <request-json>
  ```

  The helper returns `reviewed` and its `source`; an error means evidence is unavailable,
  never approval to skip review. Fetch and combine all comment pages if the CLI truncates
  them. For GitLab, provide an object with `sha`, `description` and the complete `notes` array
  (each note has `body`). Use the request's freshly fetched head in either format.
- **May clash.** Its changed files overlap an earlier request in this run, or changes to its
  base since the merge base. Use the earlier requests' file lists and
  `gh api "repos/{owner}/{repo}/compare/<headRefOid>...<baseRefName>" --jq '.files[].filename'`.
  Paginate or use a local Git diff if the API truncates the file list.

Record review reasons and overlapping files. Requests needing neither condition proceed to
step 4, where their head and review status must still be rechecked. A matching description or
comment does not override overlap: review combined behavior whenever files may clash.

## 3. Review and fix in isolated worktrees

Create a separate Git worktree and local branch for each request needing review. Fetch its
exact remote head and base, including fork branches, without switching or modifying the user's
checkout. Verify the worktree HEAD matches the fetched request head. Track its path, local
branch and remote push destination. Never reuse an unrelated worktree.

When Codex delegation is available, launch independent workers in parallel and give each its
absolute worktree path, request number, base branch, host, push destination and review reasons.
Tell each worker to run all Git and shell operations in that worktree. Codex workers share the
filesystem; spawning a worker does not create a worktree. If delegation is unavailable, process
the same worktrees sequentially yourself.

Each worker must:

1. Read the request description and repository instructions. If the request clashes with its
   base, merge the fetched base into the request branch before reviewing. If that conflicts,
   stop and report it as blocking.
2. Run Codex's built-in review against the fetched base. From the worktree, use
   `codex review -c model_reasoning_effort='"high"' --base origin/<baseRefName>` when the CLI is
   available, or the host's built-in review capability with the same scope. Adjust the remote
   reference to the actual fetched base. Do not use Claude's Skill tool or `--fix`: Codex review
   reports findings, and fixing them is a separate step. If built-in review is unavailable,
   report the request as blocking; do not invent a review marker.
3. For overlaps with other requests, inspect their diffs and check combined behavior: removed
   symbols, changed signatures, colliding migrations and behavior one request relies on.
4. Implement only critical fixes: correctness bugs, data loss, security holes, broken migrations,
   failing builds or tests, and integration breaks between overlapping requests. Do not make
   style-only or simplification changes. If a fix needs a design decision, report it as blocking.
5. Run repository-required checks. Use `make format`, `make check`, `make test` only when those
   targets exist and are the repository's prescribed checks. Fix failures caused by the changes;
   report unrelated failures. Verify the final diff, including fixes and any base merge.
6. Commit needed changes and push to the request's actual head branch. Never force-push. If
   pushing to a fork is unauthorized or rejected, stop that request and report it as blocking.
7. Unless anything is blocking, fetch the remote request head again. It must equal the reviewed
   worktree HEAD. Post the exact `Reviewed at <SHA>` first line and a second line such as
   `merge-prs: Codex built-in review; critical fixes verified`. Use a temporary body file with
   `gh pr comment <n> --body-file <file>`, or a properly quoted GitLab API note. Do not mark an
   unseen concurrent commit as reviewed.
8. Report request number, reviewed SHA, findings, fixes and commits, check results, blocking
   issues, and the worktree path and local branch.

## 4. Merge sequentially

For each request in the chosen order:

1. Inspect worker fixes and their final diff. Skip incorrect or excessive fixes, blocking issues
   and failed checks. Refresh request state and current remote head.
2. If it is now behind its base, update it using `gh pr update-branch <n>` or the GitLab equivalent.
   A conflict blocks the request. Any update that changes its head invalidates the review marker:
   repeat review and verification at that head, including overlaps with requests already merged.
3. Re-read the description and comments and confirm exact review evidence exists for the
   current head using the same helper. If another commit appeared,
   repeat review at that head before merging. Stop and report repeated concurrent changes rather
   than chasing a moving branch indefinitely.
4. Wait for required CI using `gh pr checks <n> --watch` or GitLab pipeline status. Observe waits
   through bounded polls and keep the user informed. Skip failed or unresolved required checks;
   report when no checks are configured.
5. Refresh the head again and merge only the SHA whose review and CI passed:
   `gh pr merge <n> --squash --match-head-commit <reviewed-head>` on GitHub, or
   `glab mr merge <n> --squash --auto-merge=false --sha <reviewed-head> --yes` on GitLab. If branch protection
   prevents an immediate merge, report it; do not bypass protection or claim a queued merge
   completed. Verify the server reports the request merged. Then remove its merged remote
   source branch through the hosting API when permitted, after confirming the branch still
   points to the merged head and is not the default or a protected branch. Preserve local
   branches and worktrees for step 7; GitHub's `--delete-branch` may delete local branches too.

## 5. Release claims

For every request this run labelled, merged or skipped, remove only the `reviewing` label it
added: `gh pr edit <n> --remove-label reviewing`, or the GitLab equivalent. Do this on early
exit too. Report any release that failed so it does not silently hide a request from later runs.

## 6. Report

Give a table: request | review this run (already reviewed / unreviewed / overlap) | critical
issues | fixes | merged or skipped, with reason. Include checks and unresolved claims where
relevant. Distinguish confirmed merges from queued or failed attempts.

## 7. Offer worktree cleanup

List only worktrees and local branches created by this run, with their request, merge status
and whether they contain uncommitted or unpushed work. Ask which to delete using an available
interactive question mechanism, or ask in chat and wait. Explicit skill invocation authorizes
merging and associated remote branch deletion, not removal of these local worktrees.

Remove only the selected worktrees with `git worktree remove <path>`, then their selected local
branches. Record branch tip SHAs before deleting. If removal refuses, report it and leave the
worktree; never add `--force` without explicit authorization. Prune stale worktree metadata
after approved removals. Mention a wider cleanup skill only if one is installed.
