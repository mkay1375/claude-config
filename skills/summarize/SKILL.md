---
name: summarize
description: Summarize an input — pasted text, a file, a URL, or something earlier in the conversation — as one paragraph followed by a bulleted or numbered list, shaped around what the user wants from it.
argument-hint: "[what to summarize] [what you want from it: focus, audience, length]"
disable-model-invocation: true
---

Summarize an input for the user. Their request: $ARGUMENTS

## 1. Find the input

- A file path → read the whole file (every page of a PDF, every sheet that matters).
- A URL → fetch it.
- Pasted text → use it as given.
- Nothing named, or "this" / "above" → the most recent substantial content in this conversation
  (the last pasted text, file, or your previous answer).

If there is still no clear input, ask once which one — do not guess between two candidates.

## 2. Work out what the user wants

Read the request for a focus ("the risks", "what changed", "what I need to do"), an audience
("for the CEO", "for a new developer"), and a length. When no focus is given, summarize for
someone who has not read the input and needs its main point and what follows from it.
The focus decides what goes in; material outside it is left out, not squeezed in.

## 3. Write it in this shape

**One paragraph** (3–5 sentences) that opens with the single most important point, then gives
the context needed to understand it. It must stand on its own: a reader who stops here has the
gist.

**Then one list** that carries the details:

- **Numbered** when order matters — steps, a sequence of events, a ranking, priorities.
- **Bullets** when the items are parallel — findings, risks, decisions, features.

Aim for 3–7 items. Each item is one line, leads with its key word or fact in **bold** where that
helps scanning, and adds something the paragraph did not already say. Use one level of nesting at
most, and only when an item genuinely has parts.

## Rules

- **Faithful.** Only what the input says. Keep numbers, names, dates and decisions exact. No
  opinions or recommendations unless the user asked for them; if they did, mark them as yours.
- **Flag gaps.** If the input is ambiguous, contradicts itself, or does not cover what the user
  asked about, say so in one short line after the list rather than filling the gap.
- **Same language as the request** (Farsi request → Farsi summary), unless the user asks
  otherwise. Keep code, paths, commands and identifiers as written.
- **No framing.** No "Here is a summary" preamble, no closing offer to expand.
