# Codex migration

From this repository, migrate cleanup, merge-prs, structured-question desktop
notifications and the Pydantic AI plugin in one command:

```sh
rtk proxy python3 codex/install.py --dry-run
rtk proxy python3 codex/install.py
```

Requires Python 3.11+, `rtk`, `codex`, and an existing valid Pydantic AI Claude
plugin cache. With no cache, supply `--source /path/to/pydantic-skills/plugins/ai`.
Source validation and existing hooks/config parsing happen before any writes.
Claude's original files are only read. Upstream plugin documentation is copied
unchanged through Codex's native local marketplace installer.

The default replaces `~/.agents/skills/cleanup` and `merge-prs`, archives/removes
`review-merge-prs` from both `~/.agents/skills` and `<CODEX_HOME>/skills`, copies
the question notifier, and appends its hook without reordering existing groups.
Existing RTK and SessionStart hooks and trust indices are preserved. The native
plugin installer owns Codex config changes; this script does not rewrite model,
trust or other preferences. Start a new session after installation. Run `/hooks`
in the Codex CLI to review and trust the appended hook; installation does not
forge trust. Test a real structured question in your client: hook coverage varies
and prose questions do not trigger notifications. See [hook details](hooks/README.md).

Use an isolated home to verify without touching your live skills or config:

```sh
rtk proxy python3 codex/install.py --codex-home /private/tmp/codex-migration
```

An explicit `--codex-home` defaults skills to that home's `skills` directory.
Override with `--skills-home /path/to/skills`. The plugin CLI receives that home
through `CODEX_HOME`. Dry-run validates and prints the plan without creating
files, backups, marketplaces or invoking native installation.

Before mutations, replaced directories, notifier, hook configuration, Codex
configuration and an existing adapter marketplace are copied under
`<CODEX_HOME>/backups/claude-config-<timestamp>/`. Backups are outside skill
discovery. The printed `manifest.json` records each original path, its backup
and whether it existed. Installation is not a transaction: a native plugin
failure can leave partial changes; the manifest records success or failure.

To restore, stop Codex, remove the migrated plugin with the native
`codex plugin remove pydantic-ai@claude-config` command using the same
`CODEX_HOME`, then replace each manifest `original` with its `backup`.
Remove paths marked `existed: false` instead. Restore configuration only if no
later preferences were added, or merge the saved preferences deliberately.
Native plugin caches can remain after removal. Restored hooks must be inspected
again through `/hooks` before use. Keep the backup until restoration is verified.
