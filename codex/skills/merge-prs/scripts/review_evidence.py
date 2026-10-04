#!/usr/bin/env python3
"""Check current-head review markers in a GitHub PR or normalized GitLab MR JSON."""

import argparse
import json
import re
import sys
from pathlib import Path


HTML_START = re.compile(r"<!--|<!\[CDATA\[|<\?|<(pre|script|style|textarea)(?=\s|>|$)|^ {0,3}<![A-Z]", re.IGNORECASE)


def remaining_html_end(line, end=None):
    """Track raw HTML through the line, including another opening after a close."""
    position = 0
    while True:
        if end is not None:
            closing = re.search(end, line[position:], re.IGNORECASE)
            if closing is None:
                return end
            position += closing.end()
        opening = HTML_START.search(line, position)
        if opening is None:
            return None
        token = opening.group().lstrip()
        end = (r"</" + opening.group(1) + r"\s*>" if opening.group(1) else
               {"<!--": r"-->", "<![CDATA[": r"\]\]>", "<?": r"\?>"}.get(token.upper(), r">"))
        position = opening.end()


def description_has_marker(body, marker):
    """Require a top-level paragraph boundary and reject fenced/HTML examples."""
    fence = None
    html_end = None
    html_until_blank = False
    lines = body.splitlines()
    for index, line in enumerate(lines):
        if html_end is not None:
            html_end = remaining_html_end(line, html_end)
            continue
        if html_until_blank:
            if line.strip():
                html_end = remaining_html_end(line)
                continue
            html_until_blank = False
        delimiter = re.match(r"^ {0,3}(`{3,}|~{3,})(.*)$", line)
        if fence is not None:
            if delimiter:
                token, rest = delimiter.groups()
                if token[0] == fence[0] and len(token) >= len(fence) and not rest.strip():
                    fence = None
            continue
        if delimiter:
            token, rest = delimiter.groups()
            fence = token
            continue
        # Raw HTML blocks/comments remain masked across blank lines. Be conservative
        # about inline starts too: their content can be hidden by the renderer.
        if HTML_START.search(line):
            html_end = remaining_html_end(line)
            continue
        if re.match(r"^ {0,3}</?[A-Za-z][A-Za-z0-9-]*(?=\s|/?>|$)", line):
            # Generic HTML blocks end at a blank line, as in CommonMark. We do
            # not attempt to interpret ambiguous markup as positive evidence.
            html_until_blank = True
            continue
        if line == marker and (index == 0 or not lines[index - 1].strip()):
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
