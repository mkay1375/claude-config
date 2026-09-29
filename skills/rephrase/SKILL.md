---
name: rephrase
description: Rewrite your previous answer so it is easier to understand and shorter, keeping every fact and decision it carried.
argument-hint: "[what to focus on or who it is for]"
disable-model-invocation: true
---

Rewrite your previous answer in this conversation so it is easier to understand and more concise.
Extra guidance from the user, if any: $ARGUMENTS

Rules:

- **Keep the substance.** Every fact, number, decision, warning and next step in the original stays.
  Do not add new claims, and do not redo the work — this is a rewrite, not a new answer.
- **Lead with the answer.** The first sentence says the conclusion or the thing the reader must
  act on. Background comes after, only if it is needed.
- **Plain words.** Short sentences, everyday vocabulary. Explain a technical term in a few words
  the first time it appears, or replace it with a plain one when nothing is lost.
- **Cut hard.** Drop filler, hedging, repetition, restated context, and anything the reader already
  knows. Aim for roughly half the original length or less.
- **Structure only where it helps.** Use a short list for steps or parallel items, a small table for
  comparisons. Do not turn flowing reasoning into bullet fragments.
- **Same language** as the original answer (Farsi stays Farsi, English stays English). Keep code,
  paths, commands and identifiers exactly as they were.

Output only the rewritten answer — no preamble such as "Here is a simpler version", and no note
about what you changed.
