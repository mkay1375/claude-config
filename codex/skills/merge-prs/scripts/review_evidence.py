#!/usr/bin/env python3
"""Check current-head review markers in a GitHub PR or normalized GitLab MR JSON."""

import argparse
import json
import re
import sys
from pathlib import Path


def description_has_marker(body, marker):
    """Ignore fenced examples; only an exact, standalone line records a review."""
    fence = None
    for line in body.splitlines():
        delimiter = re.match(r"^ {0,3}(`{3,}|~{3,})(.*)$", line)
        if delimiter:
            token, rest = delimiter.groups()
            if fence is None:
                fence = token
            elif token[0] == fence[0] and len(token) >= len(fence) and not rest.strip():
                fence = None
            continue
        if fence is None and line == marker:
            return True
    return False


def review_evidence(request):
    head = request.get("headRefOid", request.get("sha"))
    if not isinstance(head, str) or not re.fullmatch(r"[0-9a-f]{40}", head):
        raise ValueError("A full, current 40-character headRefOid or sha is required")
    marker = "Reviewed at " + head
    body = request.get("body", request.get("description")) or ""
    if not isinstance(body, str):
        raise ValueError("The request description must be text")
    if description_has_marker(body, marker):
        return {"head": head, "reviewed": True, "source": "description"}
    comments = request.get("comments", request.get("notes", []))
    if not isinstance(comments, list):
        raise ValueError("comments or notes must be a complete JSON array")
    for index, comment in enumerate(comments):
        text = comment.get("body") or ""
        lines = text.splitlines()
        if lines and lines[0] == marker:
            return {"head": head, "reviewed": True, "source": "comment", "index": index}
    return {"head": head, "reviewed": False, "source": None}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("request", help="JSON file, or - to read standard input")
    args = parser.parse_args()
    try:
        data = json.load(sys.stdin) if args.request == "-" else json.loads(Path(args.request).read_text())
        print(json.dumps(review_evidence(data)))
    except (OSError, ValueError, TypeError, AttributeError) as error:
        parser.exit(2, f"Review evidence unavailable: {error}\n")


if __name__ == "__main__":
    main()
