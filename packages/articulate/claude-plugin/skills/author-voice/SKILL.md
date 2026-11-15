---
name: author-voice
description: Use when the user asks to compare a draft with their own writing voice, to run an authorship interview on their draft, or to shape their own draft toward a voice profile they built with articulate voice learn. Articulate reads one profile from the user's local voice store, asks questions only the author can answer, and shapes only text the user says is theirs.
---

# Work in the author's own voice with Articulate

Use the Articulate tools exposed by the current host: `interview`,
`voice_compare`, `voice_apply_plan` and `edit_submit`. Match tools by their
Articulate server and short name. Never invent a tool result when a tool is
missing.

The profile is built on the user's computer with
`articulate voice learn FILES --name NAME --mine`. That command comes with the
separate Articulate command line (PyPI package `articulate-writing`), which
this plugin does not install. No tool here builds, exports or deletes a
profile. If the user has none, tell them that command, say where it comes from,
and stop.

## Interview

1. Call `interview` with the draft text, and `voice_name` when the user names a
   profile.
2. Present the questions with their line numbers and wait for the user. Never
   answer a question yourself and never guess what the user would say.
3. Use only the user's own words as `author_text` in a later edit.

## Compare

Call `voice_compare` with the draft and the profile name. Report each feature
that sits above or below the user's range, and the located stretches. There is
no total score. Keep the `scope` line.

## Shape the user's own draft

1. Ask whether the draft is the user's own writing. Call `voice_apply_plan`
   with `authored_by_user: true` only after the user says yes.
2. Follow the plan's instructions with its `masked_text`. Shape rhythm,
   openings and stance toward the described habits. Never add an experience,
   memory, place, date, feeling or opinion the draft does not contain; leave
   `[author: question]` where the user's perspective would help.
3. Call `edit_submit` with the original text, the rewrite, the `plan_id` and the
   same `author_text`. Show refused paragraphs and the before and after counts.

## Rules

- The house voice does not apply to the user's text.
- Keep every AI-assistance disclosure exactly as written.
- A profile that belongs to another owner is refused; do not work around it.
