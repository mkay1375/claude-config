"""Run the migration against disposable homes, with native plugin calls isolated."""

import contextlib
import importlib.util
import io
import json
from pathlib import Path
import shlex
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("codex_install", Path(__file__).parents[1] / "install.py")
installer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(installer)


class InstallTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.home = self.root / "codex home's directory"
        self.skills = self.root / "agent-skills"
        self.home.mkdir()
        self.skills.mkdir()
        self.source = self.root / "pydantic-source"
        (self.source / ".claude-plugin").mkdir(parents=True)
        (self.source / ".claude-plugin/plugin.json").write_text('{"name":"ai","version":"0.1.0"}')
        skill = self.source / "skills/building-pydantic-ai-agents"
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text("---\nname: building-pydantic-ai-agents\nlicense: MIT\n---\n")
        self.hooks = {"version": 1, "hooks": {
            "PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": "rtk rewrite"}]}],
            "SessionStart": [{"hooks": [{"type": "command", "command": "other-sessions.sh"}]}]}}
        (self.home / "hooks.json").write_text(json.dumps(self.hooks))
        self.preferences = 'model = "gpt-6"\n[hooks]\ntrusted = ["old-hash"]\n'
        (self.home / "config.toml").write_text(self.preferences)
        self.addCleanup(patch.stopall)
        patch.object(installer.shutil, "which", return_value="/fixture/bin/tool").start()
        self.native = patch.object(installer.plugin, "install", side_effect=self.fake_native_install).start()

    def fake_native_install(self, home, source):
        installer.plugin.prepare_marketplace(home, source)
        config = home / "config.toml"
        text = config.read_text() if config.exists() else ""
        if "[plugins.pydantic]" not in text:
            config.write_text(text + '\n[plugins.pydantic]\nenabled = true\n')
        return {"installed": True, "enabled": True, "skill_discovered": True}

    def install(self, **kwargs):
        return installer.migrate(self.home, self.skills, self.source, **kwargs)

    def test_migration_preserves_hooks_order_preferences_and_discovery(self):
        result = self.install()
        hooks = json.loads((self.home / "hooks.json").read_text())
        self.assertEqual(hooks["version"], self.hooks["version"])
        self.assertEqual(hooks["hooks"]["SessionStart"], self.hooks["hooks"]["SessionStart"])
        self.assertEqual(hooks["hooks"]["PreToolUse"][0], self.hooks["hooks"]["PreToolUse"][0])
        self.assertEqual(len(hooks["hooks"]["PreToolUse"]), 2)
        script = self.home / "hooks/question-notify.py"
        action = hooks["hooks"]["PreToolUse"][-1]["hooks"][0]
        self.assertEqual(shlex.split(action["command"]), ["python3", str(script)])
        self.assertIn(str(script), action["commandWindows"])
        self.assertTrue((self.home / "config.toml").read_text().startswith(self.preferences))
        self.assertIn("allow_implicit_invocation: true", (self.skills / "merge-prs/agents/openai.yaml").read_text())
        self.assertTrue((self.skills / "merge-prs/scripts/review_evidence.py").is_file())
        self.assertTrue((self.skills / "cleanup/SKILL.md").is_file())
        self.assertTrue(Path(result["backup_manifest"]).is_file())

    def test_legacy_copies_are_archived_outside_discovery_and_removed(self):
        old_paths = [self.skills / "review-merge-prs", self.home / "skills/review-merge-prs"]
        for index, old in enumerate(old_paths):
            old.mkdir(parents=True)
            (old / "SKILL.md").write_text(f"legacy copy {index}")
        existing = self.skills / "merge-prs"
        existing.mkdir()
        (existing / "SKILL.md").write_text("previous merge skill")
        result = self.install()
        manifest = json.loads(Path(result["backup_manifest"]).read_text())
        entries = {entry["original"]: entry for entry in manifest["entries"]}
        for index, old in enumerate(old_paths):
            self.assertFalse(old.exists())
            saved = Path(entries[str(old)]["backup"])
            self.assertEqual((saved / "SKILL.md").read_text(), f"legacy copy {index}")
            self.assertFalse(saved.is_relative_to(self.skills))
            self.assertFalse(saved.is_relative_to(self.home / "skills"))
        self.assertEqual((Path(entries[str(existing)]["backup"]) / "SKILL.md").read_text(), "previous merge skill")

    def test_rerun_does_not_duplicate_or_reorder_hook_groups(self):
        self.install()
        hooks_bytes = (self.home / "hooks.json").read_bytes()
        self.install()
        self.assertEqual((self.home / "hooks.json").read_bytes(), hooks_bytes)

    def test_dry_run_does_not_write_or_call_native_installer(self):
        before = {path.relative_to(self.root): path.read_bytes() for path in self.root.rglob("*") if path.is_file()}
        result = self.install(dry_run=True)
        after = {path.relative_to(self.root): path.read_bytes() for path in self.root.rglob("*") if path.is_file()}
        self.assertEqual(before, after)
        self.assertTrue(result["dry_run"])
        self.assertFalse((self.home / "backups").exists())
        self.native.assert_not_called()

    def test_invalid_hooks_fail_before_backups_or_native_changes(self):
        for data in [{"hooks": []}, {"hooks": {"PreToolUse": "bad"}},
                     {"hooks": {"PreToolUse": [{"hooks": [{"type": "command"}]}]}}]:
            with self.subTest(data=data):
                (self.home / "hooks.json").write_text(json.dumps(data))
                with self.assertRaises(ValueError):
                    self.install()
                self.assertFalse((self.home / "backups").exists())
                self.assertEqual((self.home / "config.toml").read_text(), self.preferences)
        self.native.assert_not_called()

    def test_invalid_source_fails_before_any_writes(self):
        (self.source / "skills/building-pydantic-ai-agents/SKILL.md").unlink()
        with self.assertRaises(ValueError):
            self.install()
        self.assertFalse((self.home / "backups").exists())
        self.native.assert_not_called()

    def test_native_failure_records_partial_state_and_original_config(self):
        def fail(home, source):
            (home / "config.toml").write_text(self.preferences + "# partial native edit\n")
            raise RuntimeError("native verification failed")
        self.native.side_effect = fail
        with self.assertRaisesRegex(RuntimeError, "changes may be partial"):
            self.install()
        manifest_file, = (self.home / "backups").glob("*/manifest.json")
        manifest = json.loads(manifest_file.read_text())
        self.assertEqual(manifest["status"], "failed")
        saved = next(entry for entry in manifest["entries"] if entry["original"] == str(self.home / "config.toml"))
        self.assertEqual(Path(saved["backup"]).read_text(), self.preferences)
        self.assertFalse((self.skills / "merge-prs").exists())

    def test_concurrent_hook_change_is_preserved(self):
        def update_hooks(home, source):
            (home / "hooks.json").write_text('{"hooks":{},"concurrent":true}')
            return {"installed": True}
        self.native.side_effect = update_hooks
        with self.assertRaisesRegex(RuntimeError, "changed concurrently"):
            self.install()
        self.assertTrue(json.loads((self.home / "hooks.json").read_text())["concurrent"])

    def test_custom_home_cli_defaults_to_isolated_skills(self):
        with patch.object(installer, "migrate", return_value={"dry_run": True}) as migrate, contextlib.redirect_stdout(io.StringIO()):
            installer.main(["--codex-home", str(self.home), "--source", str(self.source), "--dry-run"])
        self.assertEqual(migrate.call_args.args[:2], (self.home, self.home / "skills"))

    def test_windows_path_with_shell_punctuation_is_quoted(self):
        script = Path("C:/codex&home/hooks/question-notify.py")
        action = installer.question_group(script)["hooks"][0]
        self.assertEqual(action["commandWindows"], 'py -3 "' + str(script) + '"')


if __name__ == "__main__":
    unittest.main()
