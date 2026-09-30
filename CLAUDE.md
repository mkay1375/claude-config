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
