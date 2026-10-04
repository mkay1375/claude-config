#!/usr/bin/env python3
"""Notify for structured Codex questions; --dry-run emits the command without running it."""

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys


QUESTION_TOOLS = {"request_user_input", "request_user_input_async"}
TITLE = "Codex"
APPLE_SCRIPT = '''on run argv
display notification (item 1 of argv) with title "Codex" sound name "Glass"
end run'''
POWERSHELL_SCRIPT = '''
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
$x = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
$t = $x.GetElementsByTagName("text")
$t.Item(0).AppendChild($x.CreateTextNode("Codex")) | Out-Null
$t.Item(1).AppendChild($x.CreateTextNode($env:CODEX_QUESTION_NOTIFY_MSG)) | Out-Null
$app = "{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\\WindowsPowerShell\\v1.0\\powershell.exe"
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($app).Show([Windows.UI.Notifications.ToastNotification]::new($x))
'''


def question_message(payload):
    """Read only the question-tool input, never recursively scan unrelated content."""
    if not isinstance(payload, dict):
        return None
    if payload.get("hook_event_name") != "PreToolUse":
        return None
    tool = payload.get("tool_name")
    if not isinstance(tool, str) or tool not in QUESTION_TOOLS:
        return None
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return None
    questions = tool_input.get("questions")
    values = []
    if isinstance(questions, list):
        for entry in questions:
            if not isinstance(entry, dict):
                continue
            # Codex's async input tool puts the prompt in title; sync uses question.
            question = entry.get("title") if tool == "request_user_input_async" else None
            if not isinstance(question, str) or not question.strip():
                question = entry.get("question")
            if isinstance(question, str):
                question = " ".join(question.replace("\0", " ").split())
                if question:
                    values.append(question)
    # Some clients expose an async tool with one top-level question instead.
    if not values and tool == "request_user_input_async":
        question = tool_input.get("question")
        if isinstance(question, str):
            question = " ".join(question.replace("\0", " ").split())
            if question:
                values.append(question)
    if not values:
        return None
    return values[0] + (f" (+{len(values) - 1} more)" if len(values) > 1 else "")


def notification_command(message, system, environment):
    """Return argv plus environment additions. Question text never becomes code."""
    if system == "macos":
        return ["osascript", "-e", APPLE_SCRIPT, "--", message], {}
    if system == "linux":
        return ["notify-send", "--", TITLE, message], {}
    if system in {"windows", "wsl"}:
        additions = {"CODEX_QUESTION_NOTIFY_MSG": message}
        if system == "wsl":
            entries = [entry for entry in environment.get("WSLENV", "").split(":")
                       if entry and entry.split("/", 1)[0] != "CODEX_QUESTION_NOTIFY_MSG"]
            additions["WSLENV"] = ":".join(entries + ["CODEX_QUESTION_NOTIFY_MSG/u"])
        return ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
                POWERSHELL_SCRIPT], additions
    return [], {}


def current_system():
    name = platform.system()
    if name == "Darwin":
        return "macos" if shutil.which("osascript") else None
    if name == "Windows" or name.startswith(("MINGW", "MSYS", "CYGWIN")):
        return "windows" if shutil.which("powershell.exe") else None
    if name == "Linux":
        if "microsoft" in platform.release().lower() and shutil.which("powershell.exe"):
            return "wsl"
        return "linux" if shutil.which("notify-send") else None
    return None


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--platform", choices=["macos", "linux", "windows", "wsl"],
                        help="Override platform for dry-run only")
    args = parser.parse_args(argv)
    if args.platform and not args.dry_run:
        parser.error("--platform requires --dry-run")
    try:
        payload = json.load(sys.stdin)
    except (ValueError, UnicodeError):
        return 0
    message = question_message(payload)
    if not message:
        return 0
    command, additions = notification_command(
        message, args.platform or current_system(), os.environ)
    if args.dry_run:
        print(json.dumps({"message": message, "argv": command, "env": additions},
                         ensure_ascii=True))
    elif command:
        try:
            subprocess.run(command, env={**os.environ, **additions},
                           stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, timeout=5, check=False)
        except (OSError, ValueError, UnicodeError, subprocess.TimeoutExpired):
            pass  # A missing desktop/session must never block the question.
    return 0


if __name__ == "__main__":
    sys.exit(main())
