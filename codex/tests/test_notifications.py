import contextlib
import importlib.util
import io
import json
from pathlib import Path
import re
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("question_notify", ROOT / "hooks/question-notify.py")
notify = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(notify)


def event(tool="request_user_input", questions=None, hook="PreToolUse"):
    return {"hook_event_name": hook, "tool_name": tool,
            "tool_input": {"questions": questions if questions is not None else
                           [{"question": 'Use "main" or feature?'}]}}


class QuestionParsingTests(unittest.TestCase):
    def test_actual_question_and_count(self):
        payload = event(questions=[{"question": " \n Which branch?\n"},
                                   {"question": "Who reviews?"}, {"question": ""}])
        self.assertEqual(notify.question_message(payload), "Which branch? (+1 more)")

    def test_unrelated_tools_and_events_do_not_notify(self):
        for payload in [event(tool="Bash"), event(tool="mcp__x__request_user_input"),
                        event(tool="request_user_input_extra"), event(hook="PostToolUse"),
                        {"hook_event_name": "Notification", "message": "Waiting"},
                        {"hook_event_name": "PreToolUse", "tool_name": "request_user_input",
                         "question": "Wrong nesting?", "tool_input": {}},
                        None, [], event(tool=[]), event(questions=42)]:
            with self.subTest(payload=payload):
                self.assertIsNone(notify.question_message(payload))

    def test_async_array_and_single_question(self):
        self.assertEqual(notify.question_message(event(tool="request_user_input_async")),
                         'Use "main" or feature?')
        payload = event(tool="request_user_input_async")
        payload["tool_input"] = {"question": "Which audience?", "task_handle": "audience"}
        self.assertEqual(notify.question_message(payload), "Which audience?")
        payload["tool_name"] = "request_user_input"
        self.assertIsNone(notify.question_message(payload))

    def test_codex_async_title_prompts_and_count(self):
        payload = event(tool="request_user_input_async", questions=[
            {"title": "Which audience?", "options": ["Developers", "Managers"]},
            {"title": "How detailed?"}, {"title": ""}])
        self.assertEqual(notify.question_message(payload), "Which audience? (+1 more)")
        stdout = io.StringIO()
        with patch("sys.stdin", io.StringIO(json.dumps(payload))), \
             patch.object(notify.subprocess, "run") as run, \
             contextlib.redirect_stdout(stdout):
            self.assertEqual(notify.main(["--dry-run", "--platform", "macos"]), 0)
        run.assert_not_called()
        self.assertEqual(json.loads(stdout.getvalue())["argv"][-1],
                         "Which audience? (+1 more)")
        payload["tool_name"] = "request_user_input"
        self.assertIsNone(notify.question_message(payload))

    def test_json_unicode_quotes_controls_and_invalid_entries(self):
        payload = json.loads(r'{"hook_event_name":"PreToolUse","tool_name":"request_user_input",'
                             r'"tool_input":{"questions":[null,{}, {"question":false},'
                             r'{"question":"\u06a9\u062f \"main\"\nnow\u0000please?"}]}}')
        self.assertEqual(notify.question_message(payload), 'کد "main" now please?')


class NotificationCommandTests(unittest.TestCase):
    MESSAGE = '-e "quoted"; $(touch /tmp/nope) `whoami` <x>&\nکد'

    def test_macos_passes_text_as_one_argument(self):
        argv, env = notify.notification_command(self.MESSAGE, "macos", {})
        self.assertEqual(argv[-2:], ["--", self.MESSAGE])
        self.assertNotIn(self.MESSAGE, argv[2])
        self.assertEqual(env, {})

    def test_linux_stops_option_parsing(self):
        argv, env = notify.notification_command(self.MESSAGE, "linux", {})
        self.assertEqual(argv, ["notify-send", "--", "Codex", self.MESSAGE])
        self.assertEqual(env, {})

    def test_windows_uses_environment_and_static_xml_code(self):
        argv, env = notify.notification_command(self.MESSAGE, "windows", {})
        self.assertEqual(env["CODEX_QUESTION_NOTIFY_MSG"], self.MESSAGE)
        self.assertNotIn(self.MESSAGE, " ".join(argv))
        self.assertIn("CreateTextNode($env:CODEX_QUESTION_NOTIFY_MSG)", argv[-1])

    def test_wsl_preserves_existing_exports_without_duplicate(self):
        _, env = notify.notification_command(self.MESSAGE, "wsl",
                  {"WSLENV": "PATH/l:CODEX_QUESTION_NOTIFY_MSG/p:OTHER/u"})
        self.assertEqual(env["WSLENV"], "PATH/l:OTHER/u:CODEX_QUESTION_NOTIFY_MSG/w")

    def test_dry_run_never_executes_alert(self):
        stdout = io.StringIO()
        with patch("sys.stdin", io.StringIO(json.dumps(event()))), \
             patch.object(notify.subprocess, "run") as run, \
             contextlib.redirect_stdout(stdout):
            self.assertEqual(notify.main(["--dry-run", "--platform", "macos"]), 0)
        run.assert_not_called()
        self.assertEqual(json.loads(stdout.getvalue())["argv"][-1], 'Use "main" or feature?')

    def test_invalid_json_and_unrelated_tools_are_silent(self):
        for value in ["bad JSON", json.dumps(event(tool="Bash")), "null"]:
            with patch("sys.stdin", io.StringIO(value)), \
                 patch.object(notify.subprocess, "run") as run, \
                 contextlib.redirect_stdout(io.StringIO()) as stdout:
                self.assertEqual(notify.main(["--dry-run"]), 0)
                run.assert_not_called()
                self.assertEqual(stdout.getvalue(), "")

    def test_delivery_error_is_nonblocking_and_quiet(self):
        for error in [OSError("missing"), notify.subprocess.TimeoutExpired("osascript", 5)]:
            with patch("sys.stdin", io.StringIO(json.dumps(event()))), \
                 patch.object(notify, "current_system", return_value="macos"), \
                 patch.object(notify.subprocess, "run", side_effect=error) as run, \
                 contextlib.redirect_stdout(io.StringIO()) as stdout:
                self.assertEqual(notify.main([]), 0)
                run.assert_called_once()
                self.assertEqual(run.call_args.kwargs["timeout"], 5)
                self.assertNotIn("shell", run.call_args.kwargs)
                self.assertEqual(stdout.getvalue(), "")

    def test_hook_snippet_is_additive_and_exact(self):
        config = json.loads((ROOT / "hooks/question-notifications.json").read_text())
        self.assertEqual(list(config["hooks"]), ["PreToolUse"])
        group, = config["hooks"]["PreToolUse"]
        for name in notify.QUESTION_TOOLS:
            self.assertIsNotNone(re.fullmatch(group["matcher"], name))
        self.assertIsNone(re.fullmatch(group["matcher"], "Bash"))
        self.assertLessEqual(group["hooks"][0]["timeout"], 7)


if __name__ == "__main__":
    unittest.main()
