import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch


SPEC = importlib.util.spec_from_file_location("other_sessions", Path(__file__).parents[1] / "other-sessions.py")
hook = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(hook)


class SessionFolders(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.project = self.root / "project"
        self.project.mkdir()

    def rollout(self, session_id, cwd=None, source="cli"):
        path = self.root / f"rollout-{session_id}.jsonl"
        path.write_text(json.dumps({"type": "session_meta", "payload": {
            "id": session_id, "cwd": str(cwd or self.project), "source": source,
        }}) + "\nCONVERSATION CONTENT MUST NOT BE READ\n")
        return path

    def invoke(self, files, payload=None, snapshot=None, code=0):
        calls = []

        def run(args, timeout):
            calls.append(args)
            if args[0] == "ps":
                # pid 10 is our shared server, pid 20 an external CLI frontend.
                output = snapshot or "10 1 /bin/codex\n20 1 /bin/codex\n99 10 python3\n"
                return subprocess.CompletedProcess(args, 0, output, "")
            output = "p10\nfcwd\nn" + str(self.project) + "\n" + "".join(f"n{path}\n" for path in files)
            return subprocess.CompletedProcess(args, code, output, "")

        output = io.StringIO()
        with patch.object(hook, "run", side_effect=run), patch.object(hook.os, "getpid", return_value=99), \
                patch.dict(os.environ, {"CODEX_THREAD_ID": "own"}), \
                patch.object(hook.sys, "stdin", io.StringIO(json.dumps(payload or {"cwd": str(self.project)}))), \
                contextlib.redirect_stdout(output):
            hook.main()
        data = output.getvalue()
        return (json.loads(data)["hookSpecificOutput"]["additionalContext"] if data else ""), calls

    def test_different_chat_folder_does_not_use_frontend_cwd(self):
        context, _ = self.invoke([self.rollout("own"), self.rollout("other", self.root / "elsewhere")])
        self.assertEqual(context, "")

    def test_other_chat_in_same_folder_on_own_server_warns(self):
        context, calls = self.invoke([self.rollout("own"), self.rollout("other")])
        self.assertIn("codex session other", context)
        self.assertNotIn("codex session own", context)
        self.assertIn(hook.POLICY, context)
        self.assertIn("10", calls[1][3].split(","))

    def test_session_metadata_wins_even_when_server_cwd_differs(self):
        other_folder = self.root / "elsewhere"
        context, _ = self.invoke([self.rollout("other", other_folder)], {"cwd": str(other_folder)})
        self.assertIn("codex session other", context)

    def test_payload_id_takes_priority_over_environment(self):
        context, _ = self.invoke([self.rollout("payload-own")], {"cwd": str(self.project), "session_id": "payload-own"})
        self.assertEqual(context, "")

    def test_own_subagent_is_not_another_session(self):
        source = {"subagent": {"thread_spawn": {"parent_thread_id": "own"}}}
        context, _ = self.invoke([self.rollout("own"), self.rollout("child", source=source)])
        self.assertEqual(context, "")

    def test_guardian_approval_helper_is_not_a_project_worker(self):
        source = {"subagent": {"other": "guardian"}}
        context, _ = self.invoke([self.rollout("own"), self.rollout("approval-helper", source=source)])
        self.assertEqual(context, "")

    def test_nested_subagents_and_duplicate_open_files(self):
        parent = {"subagent": {"thread_spawn": {"parent_thread_id": "own"}}}
        child = {"subagent": {"thread_spawn": {"parent_thread_id": "child"}}}
        other = self.rollout("other")
        context, _ = self.invoke([self.rollout("own"), self.rollout("child", source=parent),
                                  self.rollout("grandchild", source=child), other, other])
        self.assertIn("1 other agent session(s)", context)

    def test_unopened_history_is_ignored(self):
        self.rollout("closed-history")
        context, _ = self.invoke([self.rollout("own")])
        self.assertEqual(context, "")

    def test_symlink_folders_are_canonicalized(self):
        alias = self.root / "alias"
        alias.symlink_to(self.project, target_is_directory=True)
        context, _ = self.invoke([self.rollout("other", alias)])
        self.assertIn("codex session other", context)

    def test_bad_metadata_reports_unknown_without_claiming_folder_conflict(self):
        path = self.root / "rollout-broken.jsonl"
        path.write_text('{"type":"session_meta"')
        context, _ = self.invoke([path])
        self.assertIn("detection is incomplete", context)
        self.assertNotIn("loaded in", context)
        self.assertNotIn(hook.POLICY, context)

    def test_no_metadata_never_falls_back_to_process_cwd(self):
        context, _ = self.invoke([])
        self.assertIn("detection is incomplete", context)
        self.assertNotIn("loaded in", context)

    def test_partial_lsof_failure_is_reported_even_with_readable_metadata(self):
        context, _ = self.invoke([self.rollout("own")], code=1)
        self.assertIn("detection is incomplete", context)

    def test_claude_idle_filter_is_preserved(self):
        with patch.object(hook, "claude_status", return_value=None):
            context, _ = self.invoke([], snapshot="10 1 /bin/claude\n99 1 python3\n")
        self.assertEqual(context, "")

    def test_claude_same_directory_warns(self):
        with patch.object(hook, "claude_status", return_value="busy"):
            context, _ = self.invoke([], snapshot="10 1 /bin/claude\n99 1 python3\n")
        self.assertIn("claude pid 10 (busy)", context)


if __name__ == "__main__":
    unittest.main()
