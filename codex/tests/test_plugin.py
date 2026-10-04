"""Pydantic plugin source validation and adaptation checks (no network)."""

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

MODULE = Path(__file__).resolve().parents[1] / "plugins/pydantic_ai.py"
spec = importlib.util.spec_from_file_location("pydantic_ai_installer", MODULE)
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class PluginTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "source"
        (self.source / ".claude-plugin").mkdir(parents=True)
        (self.source / ".claude-plugin/plugin.json").write_text(json.dumps({
            "name": "ai", "version": "0.1.0", "author": {"name": "Pydantic"},
        }))
        self.skill = self.source / "skills" / installer.SKILL_NAME
        (self.skill / "references").mkdir(parents=True)
        (self.skill / "SKILL.md").write_text(
            "---\nname: building-pydantic-ai-agents\nlicense: MIT\n---\n"
            "[Core](./references/CORE.md)\n"
        )
        (self.skill / "references/CORE.md").write_text("Upstream reference\n")

    def test_adapter_preserves_files_and_attribution_excludes_runtime_state(self):
        (self.source / "LICENSE").write_text("MIT license fixture\n")
        (self.source / ".in_use").mkdir()
        (self.source / ".in_use/123").touch()
        market = installer.prepare_marketplace(self.root / "codex", self.source)
        plugin = market / "plugins/pydantic-ai"
        manifest = json.loads((plugin / ".codex-plugin/plugin.json").read_text())
        self.assertEqual(manifest["name"], "pydantic-ai")
        self.assertEqual(manifest["author"], {"name": "Pydantic"})
        self.assertEqual((plugin / "LICENSE").read_bytes(), (self.source / "LICENSE").read_bytes())
        self.assertEqual((plugin / "skills" / installer.SKILL_NAME / "SKILL.md").read_bytes(), (self.skill / "SKILL.md").read_bytes())
        self.assertTrue((plugin / "skills" / installer.SKILL_NAME / "references/CORE.md").is_file())
        self.assertFalse((plugin / ".in_use").exists())
        self.assertTrue((plugin / "ATTRIBUTION.txt").is_file())

    def test_content_update_changes_cache_version_and_removes_stale_files(self):
        market = installer.prepare_marketplace(self.root / "codex", self.source)
        manifest = market / "plugins/pydantic-ai/.codex-plugin/plugin.json"
        old_version = json.loads(manifest.read_text())["version"]
        (self.skill / "references/EXTRA.md").write_text("New reference\n")
        installer.prepare_marketplace(self.root / "codex", self.source)
        self.assertNotEqual(json.loads(manifest.read_text())["version"], old_version)
        (self.skill / "references/EXTRA.md").unlink()
        installer.prepare_marketplace(self.root / "codex", self.source)
        self.assertFalse((market / "plugins/pydantic-ai/skills" / installer.SKILL_NAME / "references/EXTRA.md").exists())

    def test_missing_reference_fails_before_writing(self):
        (self.skill / "references/CORE.md").unlink()
        with self.assertRaisesRegex(ValueError, "Missing or unsafe"):
            installer.prepare_marketplace(self.root / "codex", self.source)
        self.assertFalse((self.root / "codex").exists())

    def test_missing_cache_is_actionable_and_read_only(self):
        with self.assertRaisesRegex(ValueError, "No valid cached Pydantic AI"):
            installer.find_source(claude_home=self.root / "missing-claude")
        self.assertFalse((self.root / "missing-claude").exists())

    def test_unrelated_marketplace_is_preserved(self):
        market = self.root / "codex/local-marketplaces/claude-config"
        market.mkdir(parents=True)
        (market / "keep").write_text("Unrelated config")
        with self.assertRaisesRegex(ValueError, "unrelated marketplace"):
            installer.prepare_marketplace(self.root / "codex", self.source)
        self.assertEqual((market / "keep").read_text(), "Unrelated config")


if __name__ == "__main__":
    unittest.main()
