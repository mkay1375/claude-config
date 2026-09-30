@RTK.md

## Large tasks

When a task is too big to do well in one pass, split it into parts and work through them one at
a time:

1. Run the part in a subagent.
2. Commit that part.
3. Move on to the next part and repeat.

Don't start the next part until the current one is committed. Once every part is done, review
the whole change as one piece rather than reviewing each part on its own, and fix what the
review finds.

## Open PRs

When a task ends with an open PR, append one line for it to `.open-prs.txt` at the root of the
repo's main checkout, not the worktree you worked in, so every session and the reviewer see the
same file:

```bash
root="$(git rev-parse --path-format=absolute --git-common-dir)/.."
echo "<pr-url> open" >> "$root/.open-prs.txt"
```

Each line is `<pr-url> <status>`, optionally followed by `# <comment>`. The status is `open`
(waiting for review) or `reviewing` (a `/review-merge-prs` run has taken it). Only append; never
rewrite lines other sessions wrote. The file is local and never committed: if
`.open-prs.txt` is missing from `$root/.git/info/exclude`, add it there.
