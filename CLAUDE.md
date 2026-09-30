@RTK.md

## Large tasks

When a task is too big to do well in one pass, split it into parts and work through them one at
a time:

1. Run the part in a subagent.
2. Commit that part.
3. Move on to the next part and repeat.

Don't start a part that depends on another until that one is committed. Parts that don't depend
on each other run at the same time: launch their subagents together, then commit each part as it
finishes. Once every part is done, review
the whole change as one piece rather than reviewing each part on its own, and fix what the
review finds.

## Marking a PR reviewed

Whenever a PR's code has been reviewed after implementation — a big task's final review, a
single `/code-review`, or any other review — and the fixes it led to are committed and pushed,
leave a PR comment whose first line is exactly

```
Reviewed at <full 40-character SHA of the PR head once the review's fixes are pushed>
```

followed by one line saying which review ran (e.g. `/code-review high --fix`). If the review
happened before the PR existed, post the comment right after opening the PR. Use
`gh pr comment <n> --body "..."` on GitHub, or
`glab api -X POST "projects/:id/merge_requests/<n>/notes" -f body="..."` for a GitLab MR
(gitlab.com or self-hosted). Any later commit on the
branch makes the PR unreviewed again; `/merge-prs` relies on this to skip PRs already reviewed.
