# Pydantic AI for Codex

`pydantic_ai.py` installs the existing Pydantic AI skill as
`pydantic-ai@claude-config` through Codex's native local marketplace support.
It discovers a valid Claude plugin cache or accepts `--source`. The repository
contains the installer, not a second copy of upstream documentation.

```sh
rtk proxy python3 codex/plugins/pydantic_ai.py
# Test in a separate home without changing your Codex settings:
rtk proxy python3 codex/plugins/pydantic_ai.py --codex-home /private/tmp/pydantic-codex
# Or provide an existing clone/cache explicitly:
rtk proxy python3 codex/plugins/pydantic_ai.py --source /path/to/pydantic-skills/plugins/ai
```

The official Claude marketplace calls its entry `pydantic-ai`, while the
upstream plugin manifest names it `ai`. Codex checks those names and rejects
the mismatch. This installer generates a Codex manifest with the matching
name and copies the MIT-licensed skill and references unchanged. It preserves
available license files, upstream author metadata, attribution, and SHA-256
provenance. It excludes Claude runtime state and installs no Claude hooks.
The adapter version includes a source-content hash so a later source update
cannot silently reuse the old installed cache.

The resulting marketplace is at
`<CODEX_HOME>/local-marketplaces/claude-config`. Installation verifies that
Codex reports the plugin installed and enabled, that the installed skill
matches the source, and that Codex discovers
`pydantic-ai:building-pydantic-ai-agents` in its model-visible skill catalog.
Start a new Codex session to see the newly installed skill.

Source availability, expected plugin/skill names, MIT declaration, and linked
reference files are checked before writing. A missing source produces an
actionable error without fetching arbitrary remote content. For integration,
call `find_source()` before making other configuration changes, then call
`install(codex_home, source)`. `--prepare-only` creates the local marketplace
without changing native installation settings.
