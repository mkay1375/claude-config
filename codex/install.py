#!/usr/bin/env python3
"""Migrate the repository's Codex skills, question hook and Pydantic AI plugin."""

from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import tomllib
import uuid

ROOT = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("pydantic_ai", ROOT / "plugins/pydantic_ai.py")
plugin = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(plugin)
SKILLS = ("cleanup", "merge-prs")


def validate_hooks(data):
    if not isinstance(data, dict) or not isinstance(data.get("hooks", {}), dict):
        raise ValueError("hooks.json must contain a hooks object")
    for event, groups in data.get("hooks", {}).items():
        if not isinstance(event, str) or not isinstance(groups, list):
            raise ValueError("Each hook event must contain an array of groups")
        for group in groups:
            if not isinstance(group, dict) or not isinstance(group.get("hooks"), list):
                raise ValueError("Each hook group must contain a hooks array")
            if "matcher" in group and not isinstance(group["matcher"], str):
                raise ValueError("Hook matchers must be strings")
            for action in group["hooks"]:
                if not isinstance(action, dict) or not isinstance(action.get("type"), str):
                    raise ValueError("Each hook action must have a type")
                if action["type"] == "command" and not isinstance(action.get("command"), str):
                    raise ValueError("Command hooks must have a command string")
                if "commandWindows" in action and not isinstance(action["commandWindows"], str):
                    raise ValueError("commandWindows must be a string")


def question_group(script):
    group = json.loads((ROOT / "hooks/question-notifications.json").read_text())["hooks"]["PreToolUse"][0]
    # Always quote the POSIX path; shlex-style escaping also handles apostrophes.
    quoted = "'" + str(script).replace("'", "'\"'\"'") + "'"
    group["hooks"][0]["command"] = "python3 " + quoted
    windows_path = subprocess.list2cmdline([str(script)])
    if not windows_path.startswith('"'):
        windows_path = '"' + windows_path + '"'
    group["hooks"][0]["commandWindows"] = "py -3 " + windows_path
    return group


def merged_hooks(data, script):
    updated = copy.deepcopy(data)
    groups = updated.setdefault("hooks", {}).setdefault("PreToolUse", [])
    group = question_group(script)
    if group not in groups:
        groups.append(group)
    return updated


def preflight(codex_home, skills_home, source=None):
    """Validate everything locally before any backup or installation writes."""
    codex_home, skills_home = codex_home.expanduser().resolve(), skills_home.expanduser().resolve()
    source = plugin.find_source(source)
    provenance = plugin.inspect_source(source)
    hooks_path = codex_home / "hooks.json"
    hooks_bytes = hooks_path.read_bytes() if hooks_path.exists() else None
    hooks = json.loads(hooks_bytes) if hooks_bytes is not None else {"hooks": {}}
    validate_hooks(hooks)
    config = codex_home / "config.toml"
    if config.exists():
        tomllib.loads(config.read_text())
    market = codex_home / "local-marketplaces/claude-config"
    if market.exists() and not (market / "pydantic-ai-provenance.json").is_file():
        raise ValueError(f"Refusing to overwrite an unrelated marketplace: {market}")
    script = codex_home / "hooks/question-notify.py"
    targets = [skills_home / name for name in SKILLS]
    legacy = list(dict.fromkeys([skills_home / "review-merge-prs", codex_home / "skills/review-merge-prs"]))
    targets += legacy + [script, hooks_path, config, market]
    for target in targets:
        if target.is_symlink():
            raise ValueError(f"Refusing to replace a symlink: {target}")
    for target in [*(skills_home / name for name in SKILLS), *legacy, market]:
        if target.exists() and not target.is_dir():
            raise ValueError(f"Expected an installation directory: {target}")
    for target in [script, hooks_path, config]:
        if target.exists() and not target.is_file():
            raise ValueError(f"Expected an installation file: {target}")
    if (codex_home / "backups").is_relative_to(skills_home):
        raise ValueError("Backup directory must be outside the discoverable skills directory")
    for name in SKILLS:
        skill = ROOT / "skills" / name / "SKILL.md"
        if not skill.is_file() or f"name: {name}\n" not in skill.read_text():
            raise ValueError(f"Missing or invalid repository skill: {skill}")
    if not (ROOT / "hooks/question-notify.py").is_file():
        raise ValueError("Missing question notification script")
    return {"codex_home": codex_home, "skills_home": skills_home, "source": source,
            "provenance": provenance, "targets": list(dict.fromkeys(targets)),
            "legacy": legacy, "script": script, "hooks_bytes": hooks_bytes,
            "hooks": merged_hooks(hooks, script)}


def atomic_text(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix="." + path.name + "-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w") as file:
            file.write(text)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def snapshot(plan):
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    backup = plan["codex_home"] / "backups" / ("claude-config-" + stamp)
    backup.mkdir(parents=True)
    backup.chmod(0o700)
    entries = []
    for index, target in enumerate(plan["targets"]):
        saved = backup / "files" / str(index)
        exists = target.exists()
        if exists:
            saved.parent.mkdir(parents=True, exist_ok=True)
            if target.is_dir():
                shutil.copytree(target, saved, symlinks=True)
            else:
                shutil.copy2(target, saved)
        entries.append({"original": str(target), "existed": exists,
                        "backup": str(saved) if exists else None})
    manifest = {"status": "backed-up", "entries": entries,
                "plugin_id": plugin.PLUGIN_ID, "source": str(plan["source"]),
                "source_sha256": plan["provenance"]["content_sha256"]}
    atomic_text(backup / "manifest.json", json.dumps(manifest, indent=2) + "\n")
    return backup, manifest


def migrate(codex_home, skills_home, source=None, dry_run=False):
    plan = preflight(codex_home, skills_home, source)
    if dry_run:
        return {"dry_run": True, "codex_home": str(plan["codex_home"]),
                "skills_home": str(plan["skills_home"]), "plugin_source": str(plan["source"]),
                "backup_targets": [str(path) for path in plan["targets"]],
                "remove_legacy": [str(path) for path in plan["legacy"] if path.exists()],
                "question_hook": question_group(plan["script"])}
    if not shutil.which("rtk") or not shutil.which("codex"):
        raise ValueError("rtk and codex must be on PATH; no installation files changed")
    backup, manifest = snapshot(plan)
    try:
        # The native installer owns config/plugin registry updates; do not edit preferences.
        result = plugin.install(plan["codex_home"], plan["source"])
        hooks_path = plan["codex_home"] / "hooks.json"
        current = hooks_path.read_bytes() if hooks_path.exists() else None
        if current != plan["hooks_bytes"]:
            raise RuntimeError("hooks.json changed concurrently; refusing to overwrite it")
        for name in SKILLS:
            destination = plan["skills_home"] / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists():
                shutil.rmtree(destination)
            shutil.copytree(ROOT / "skills" / name, destination,
                            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        plan["script"].parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / "hooks/question-notify.py", plan["script"])
        if current is None or json.loads(current) != plan["hooks"]:
            atomic_text(hooks_path, json.dumps(plan["hooks"], indent=2) + "\n")
        for legacy in plan["legacy"]:
            if legacy.exists():
                shutil.rmtree(legacy)
        manifest["status"] = "complete"
        atomic_text(backup / "manifest.json", json.dumps(manifest, indent=2) + "\n")
        return {"backup_manifest": str(backup / "manifest.json"), "skills": list(SKILLS),
                "plugin": result, "hooks": str(hooks_path)}
    except Exception as error:
        manifest.update(status="failed", error=str(error))
        atomic_text(backup / "manifest.json", json.dumps(manifest, indent=2) + "\n")
        raise RuntimeError(f"Migration stopped after backups; changes may be partial.\n"
                           f"Backup manifest: {backup / 'manifest.json'}\n{error}") from error


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--codex-home", type=Path)
    parser.add_argument("--skills-home", type=Path)
    parser.add_argument("--source", type=Path, help="Existing Pydantic AI plugin cache/clone")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    codex_home = args.codex_home or Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))
    # A custom Codex home must not accidentally replace the user's shared live skills.
    skills_home = args.skills_home or (codex_home / "skills" if args.codex_home else Path.home() / ".agents/skills")
    try:
        result = migrate(codex_home, skills_home, args.source, args.dry_run)
    except (ValueError, OSError, RuntimeError) as error:
        parser.exit(1, str(error) + "\n")
    print(json.dumps(result, indent=2))
    if not args.dry_run:
        print("Restart Codex. In the CLI, run /hooks to inspect and trust the new question hook. "
              "No hook trust records were changed.")


if __name__ == "__main__":
    main()
