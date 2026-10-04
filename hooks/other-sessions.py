#!/usr/bin/env python3
"""Codex SessionStart hook: check session folders, not a shared server's cwd."""

import json
import os
from pathlib import Path
import re
import subprocess
import sys


POLICY = """Before editing anything:
- If this task depends on another session's task being finished, wait for it to finish.
- Otherwise, do the work in a new git worktree, never in the shared checkout. Create it on a
  new branch, do the job, commit, push, open a PR, and give the user the PR link. No additional
  permission is needed to create the worktree.
Recheck before editing if another session could have started since this session-start scan.
"""


def emit(context):
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "SessionStart", "additionalContext": context,
    }}))


def run(args, timeout):
    return subprocess.run(args, text=True, capture_output=True, timeout=timeout)


def process_table(output):
    table = {}
    for line in output.splitlines():
        fields = line.strip().split(None, 2)
        if len(fields) == 3 and fields[0].isdigit() and fields[1].isdigit():
            table[int(fields[0])] = (int(fields[1]), Path(fields[2]).name)
    return table


def ancestors(table, pid):
    own = set()
    while pid > 1 and pid not in own:
        own.add(pid)
        pid = table.get(pid, (0, ""))[0]
    return own


def working_directories(output):
    directories = {}
    pid = None
    for line in output.splitlines():
        if line.startswith("p") and line[1:].isdigit():
            pid = int(line[1:])
        elif line.startswith("n") and pid is not None:
            directories[pid] = os.path.realpath(line[1:])
    return directories


def codex_sessions(output):
    """Read only the first metadata record of rollouts held open by live Codex.

    A server can own several chats, and a CLI can attach to a server whose cwd
    differs from every chat's folder. Neither process cwd nor historical files
    on disk identify the current sessions. lsof supplies the live file set.
    """
    paths = set()
    for line in output.splitlines():
        if line.startswith("n"):
            path = Path(line[1:])
            if path.name.startswith("rollout-") and path.suffix == ".jsonl":
                paths.add(path)
    sessions = {}
    unreadable = 0
    for path in paths:
        try:
            with path.open("rb") as stream:
                # Never scan conversation content or load a large transcript.
                record = json.loads(stream.readline(262144))
            metadata = record.get("payload")
            if record.get("type") != "session_meta" or not isinstance(metadata, dict):
                raise ValueError("missing session metadata")
            session_id, cwd = metadata.get("id"), metadata.get("cwd")
            if not isinstance(session_id, str) or not session_id or not isinstance(cwd, str) or not os.path.isabs(cwd):
                raise ValueError("invalid session folder")
            sessions[session_id] = dict(metadata, cwd=os.path.realpath(cwd))
        except (OSError, ValueError, AttributeError):
            unreadable += 1
    return sessions, unreadable


def belongs_to_session(sessions, session_id, own_id):
    """Exclude the current chat and its subagents, even on a shared server."""
    visited = set()
    while session_id and session_id not in visited:
        if session_id == own_id:
            return True
        visited.add(session_id)
        source = sessions.get(session_id, {}).get("source")
        if not isinstance(source, dict):
            return False
        subagent = source.get("subagent")
        spawn = subagent.get("thread_spawn") if isinstance(subagent, dict) else None
        session_id = spawn.get("parent_thread_id") if isinstance(spawn, dict) else None
        if not isinstance(session_id, str):
            return False
    return False


def is_guardian(metadata):
    # Approval-review helper threads are not independent project workers and
    # currently have no parent_thread_id with which to exclude them as ours.
    source = metadata.get("source")
    subagent = source.get("subagent") if isinstance(source, dict) else None
    return isinstance(subagent, dict) and subagent.get("other") == "guardian"


def claude_dialog_is_idle(home, session_id):
    if not isinstance(session_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", session_id):
        return False
    transcripts = list((home / ".claude/projects").glob(f"*/{session_id}.jsonl"))
    if not transcripts:
        return True  # Original Claude hook: a session without a prompt is at rest.
    try:
        # A bounded tail avoids loading large transcripts. Incomplete JSON is unknown activity.
        with transcripts[0].open("rb") as stream:
            stream.seek(0, 2)
            size = stream.tell()
            start = max(0, size - 262144)
            stream.seek(start)
            lines = stream.read().decode("utf-8").splitlines()
        if start:
            lines = lines[1:]
        for line in reversed(lines):
            entry = json.loads(line)
            if entry.get("isSidechain") or entry.get("isMeta"):
                continue
            kind = entry.get("type")
            message = entry.get("message") or {}
            content = message.get("content")
            if kind == "assistant":
                return message.get("stop_reason") == "end_turn"
            if kind == "user":
                if isinstance(content, str) and content.startswith(("<local-command-", "<command-name>")):
                    continue
                return (isinstance(content, list) and bool(content)
                        and isinstance(content[0], dict)
                        and str(content[0].get("text", "")).startswith("[Request interrupted by user"))
        return start == 0
    except (OSError, ValueError, AttributeError):
        return False


def claude_status(home, pid):
    try:
        state = json.loads((home / f".claude/sessions/{pid}.json").read_text())
        status = state.get("status")
        if status == "idle":
            return None
        if (status == "waiting" and state.get("waitingFor") == "dialog open"
                and claude_dialog_is_idle(home, state.get("sessionId"))):
            return None
        return status if isinstance(status, str) else "activity unknown"
    except (OSError, ValueError, AttributeError):
        return "activity unknown"


def main():
    try:
        payload = json.load(sys.stdin) if not sys.stdin.isatty() else {}
        if not isinstance(payload, dict):
            raise ValueError("hook input must be an object")
        cwd = payload.get("cwd") or os.getcwd()
        if not isinstance(cwd, str):
            raise ValueError("cwd must be a string")
        cwd = os.path.realpath(cwd)
        snapshot = run(["ps", "-Ao", "pid=,ppid=,comm="], 3)
        if snapshot.returncode or not snapshot.stdout.strip():
            raise RuntimeError("process listing unavailable")
        table = process_table(snapshot.stdout)
        if not table:
            raise RuntimeError("process listing could not be parsed")
        own = ancestors(table, os.getpid())
        claude = {pid: name for pid, (_, name) in table.items()
                  if name == "claude" and pid not in own}
        # Include our own server: it can host other chats too.
        codex = {pid for pid, (_, name) in table.items() if name == "codex"}
        if not claude and not codex:
            return
        others = []
        notes = []
        if claude:
            listing = run(["lsof", "-a", "-p", ",".join(map(str, claude)), "-d", "cwd", "-Fn"], 3)
            directories = working_directories(listing.stdout)
            for pid in claude:
                if directories.get(pid) == cwd:
                    status = claude_status(Path.home(), pid)
                    if status is not None:
                        others.append(f"claude pid {pid} ({status})")
            missing = set(claude) - set(directories)
            if missing:
                notes.append(f"WARNING: working directories could not be checked for {len(missing)} "
                             "Claude process(es); parallel-session detection is incomplete.")
        if codex:
            listing = run(["lsof", "-a", "-p", ",".join(map(str, codex)), "-Fn"], 3)
            sessions, unreadable = codex_sessions(listing.stdout)
            own_id = payload.get("session_id") or os.environ.get("CODEX_THREAD_ID")
            for session_id, metadata in sessions.items():
                if (metadata["cwd"] == cwd and not is_guardian(metadata)
                        and not belongs_to_session(sessions, session_id, own_id)):
                    others.append(f"codex session {session_id} (activity unknown)")
            if listing.returncode or unreadable or not sessions:
                notes.append("WARNING: some Codex session folders could not be checked; "
                             "parallel-session detection is incomplete. Process cwd is not used "
                             "as a substitute for a chat's folder.")
        if others:
            notes.insert(0, f"WARNING: {len(others)} other agent session(s) loaded in {cwd}: "
                         + ", ".join(others) + ".")
            notes.append("Codex activity cannot be classified as busy or idle from session metadata.")
        if notes:
            # Unknown folders do not establish a conflict in this checkout.
            emit("\n".join(notes) + ("\n" + POLICY if others else ""))
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as error:
        emit(f"WARNING: parallel-session check failed ({type(error).__name__}); "
             "do not assume this checkout is unused. Check other agent sessions before editing.\n"
             + POLICY)


if __name__ == "__main__":
    main()
