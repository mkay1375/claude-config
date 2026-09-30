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
