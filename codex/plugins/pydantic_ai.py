#!/usr/bin/env python3
"""Install the cached MIT Pydantic AI skill through a local Codex plugin.

No upstream documentation is vendored in this repository. The official Claude
marketplace calls this plugin pydantic-ai but its manifest calls it ai, which
Codex rejects. Only the plugin manifest is adapted; skill files stay unchanged.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

PLUGIN_ID = "pydantic-ai@claude-config"
SKILL_NAME = "building-pydantic-ai-agents"
UPSTREAM = "https://github.com/pydantic/skills/tree/main/plugins/ai"


def inspect_source(source: Path) -> dict:
    """Validate before writing any installation files; return provenance."""
    source = source.expanduser().resolve()
    manifest = source / ".claude-plugin/plugin.json"
    skill = source / "skills" / SKILL_NAME / "SKILL.md"
    if not manifest.is_file() or not skill.is_file():
        raise ValueError(f"Not a Pydantic AI plugin: {source}")
    upstream_manifest = json.loads(manifest.read_text())
    if upstream_manifest.get("name") not in {"ai", "pydantic-ai"}:
        raise ValueError(f"Unexpected plugin name in {manifest}")
    text = skill.read_text()
    frontmatter = text.split("---", 2)[1] if text.startswith("---\n") else ""
    if not re.search(r"^license:\s*MIT\s*$", frontmatter, re.MULTILINE):
        raise ValueError(f"Expected upstream MIT license declaration in {skill}")
    if not re.search(rf"^name:\s*{SKILL_NAME}\s*$", frontmatter, re.MULTILINE):
        raise ValueError(f"Unexpected skill name in {skill}")
    for relative in re.findall(r"\]\(\./([^)#]+)(?:#[^)]*)?\)", text):
        reference = (skill.parent / relative).resolve()
        if not reference.is_relative_to(skill.parent) or not reference.is_file():
            raise ValueError(f"Missing or unsafe skill reference: {relative}")
    files = []
    for path in sorted((source / "skills").rglob("*")):
        if path.is_symlink():
            raise ValueError(f"Skill symlinks are not supported: {path}")
        if path.is_file():
            files.append(path)
    digest = hashlib.sha256()
    for path in [manifest, *files]:
        digest.update(path.relative_to(source).as_posix().encode() + b"\0")
        digest.update(path.read_bytes() + b"\0")
    version = upstream_manifest.get("version", "0.1.0")
    if not isinstance(version, str) or not re.fullmatch(r"[0-9A-Za-z.+-]+", version):
        raise ValueError("Unsafe upstream plugin version")
    return {
        "source": str(source),
        "upstream": UPSTREAM,
        "upstream_manifest": upstream_manifest,
        "manifest_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
        "content_sha256": digest.hexdigest(),
        "skill_sha256": hashlib.sha256(skill.read_bytes()).hexdigest(),
        "license": "MIT (upstream skill frontmatter)",
        "version": version + "+codex." + digest.hexdigest()[:12],
    }


def find_source(source: Path | None = None, claude_home: Path | None = None) -> Path:
    """Use an explicit source or the newest valid existing Claude cache."""
    if source is not None:
        source = source.expanduser().resolve()
        inspect_source(source)
        return source
    claude_home = claude_home or Path.home() / ".claude"
    candidates = list((claude_home / "plugins/cache").glob("*/pydantic-ai/*"))
    candidates.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    for candidate in candidates:
        try:
            inspect_source(candidate)
            return candidate.resolve()
        except (ValueError, OSError, json.JSONDecodeError):
            continue
    raise ValueError(
        "No valid cached Pydantic AI plugin found. Install it in Claude first, "
        "or pass --source /path/to/pydantic-skills/plugins/ai. "
        "No installation files were changed."
    )


def prepare_marketplace(codex_home: Path, source: Path) -> Path:
    provenance = inspect_source(source)
    source = Path(provenance["source"])
    marketplace = codex_home.expanduser().resolve() / "local-marketplaces/claude-config"
    if marketplace.exists() and not (marketplace / "pydantic-ai-provenance.json").is_file():
        raise ValueError(f"Refusing to overwrite an unrelated marketplace: {marketplace}")
    marketplace.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".pydantic-ai-", dir=marketplace.parent))
    try:
        plugin = stage / "plugins/pydantic-ai"
        shutil.copytree(source / "skills", plugin / "skills")
        for filename in ("LICENSE", "LICENSE.md", "LICENSE.txt", "COPYING", "README.md"):
            path = source / filename
            if path.is_file() and not path.is_symlink():
                shutil.copy2(path, plugin / filename)
        (plugin / ".codex-plugin").mkdir()
        manifest = {
            "name": "pydantic-ai",
            "version": provenance["version"],
            "description": provenance["upstream_manifest"].get("description", "Build agents with Pydantic AI"),
            "author": provenance["upstream_manifest"].get("author", {"name": "Pydantic"}),
            "homepage": UPSTREAM,
            "license": "MIT",
            "skills": "./skills/",
        }
        (plugin / ".codex-plugin/plugin.json").write_text(json.dumps(manifest, indent=2) + "\n")
        attribution = (
            "Pydantic AI skill and references by Pydantic, licensed MIT in the "
            "upstream SKILL.md.\nSource: " + UPSTREAM + "\n"
            "Only the Codex plugin manifest was generated locally. Skill files "
            "are copied unchanged.\nSee pydantic-ai-provenance.json for source hashes.\n"
        )
        (plugin / "ATTRIBUTION.txt").write_text(attribution)
        for path in (stage, plugin):
            (path / "pydantic-ai-provenance.json").write_text(json.dumps(provenance, indent=2) + "\n")
        (stage / ".agents/plugins").mkdir(parents=True)
        catalog = {
            "name": "claude-config",
            "plugins": [{
                "name": "pydantic-ai",
                "source": {"source": "local", "path": "./plugins/pydantic-ai"},
                "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
                "category": "Developer Tools",
            }],
        }
        (stage / ".agents/plugins/marketplace.json").write_text(json.dumps(catalog, indent=2) + "\n")
        if marketplace.exists():
            shutil.rmtree(marketplace)
        stage.rename(marketplace)
    finally:
        if stage.exists():
            shutil.rmtree(stage)
    return marketplace


def _codex(codex_home: Path, *arguments: str) -> str:
    environment = dict(os.environ, CODEX_HOME=str(codex_home.expanduser().resolve()))
    result = subprocess.run(
        ["rtk", "proxy", "codex", *arguments], env=environment,
        capture_output=True, text=True, timeout=60,
    )
    if result.returncode:
        raise RuntimeError(f"codex {' '.join(arguments)} failed:\n{result.stderr.strip()}")
    return result.stdout


def install(codex_home: Path, source: Path | None = None) -> dict:
    """Create the adapter, install natively, and verify skill discovery."""
    source = find_source(source)
    provenance = inspect_source(source)
    marketplace = prepare_marketplace(codex_home, source)
    _codex(codex_home, "plugin", "marketplace", "add", str(marketplace), "--json")
    result = json.loads(_codex(codex_home, "plugin", "add", PLUGIN_ID, "--json"))
    catalog = json.loads(_codex(codex_home, "plugin", "list", "--json"))
    installed = next((item for item in catalog["installed"] if item["pluginId"] == PLUGIN_ID), {})
    if not installed.get("installed") or not installed.get("enabled"):
        raise RuntimeError(f"Native catalog did not verify {PLUGIN_ID} installed and enabled")
    skill = Path(result["installedPath"]) / "skills" / SKILL_NAME / "SKILL.md"
    if hashlib.sha256(skill.read_bytes()).hexdigest() != provenance["skill_sha256"]:
        raise RuntimeError("Installed Pydantic AI skill differs from upstream source")
    prompt = json.loads(_codex(codex_home, "debug", "prompt-input"))
    discovery = "\n".join(
        block.get("text", "") for item in prompt for block in item.get("content", [])
    )
    if f"pydantic-ai:{SKILL_NAME}:" not in discovery:
        raise RuntimeError("Installed Pydantic AI skill was not discovered by Codex")
    return {
        "plugin_id": PLUGIN_ID,
        "installed_path": result["installedPath"],
        "installed": True,
        "enabled": True,
        "skill_discovered": True,
        "skill_unchanged": True,
        "manifest_sha256": provenance["manifest_sha256"],
        "content_sha256": provenance["content_sha256"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, help="Existing upstream Pydantic AI plugin directory")
    parser.add_argument("--codex-home", type=Path, default=Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))))
    parser.add_argument("--prepare-only", action="store_true", help="Create the marketplace without native installation")
    arguments = parser.parse_args()
    try:
        source = find_source(arguments.source)
        if arguments.prepare_only:
            print(json.dumps({"marketplace": str(prepare_marketplace(arguments.codex_home, source))}))
        else:
            print(json.dumps(install(arguments.codex_home, source), indent=2))
    except (ValueError, RuntimeError, OSError, subprocess.TimeoutExpired) as error:
        parser.exit(1, str(error) + "\n")


if __name__ == "__main__":
    main()
