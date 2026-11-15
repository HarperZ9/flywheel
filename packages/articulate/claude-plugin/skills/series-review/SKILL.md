---
name: series-review
description: Use when the user asks to review several essays, posts or chapters together as a series, to check whether a set of titles follows one formula, or to find repeated paragraph scaffolds, shared phrases, even rhythm or missing first-person perspective across documents. Articulate reads the documents on the user's computer, reports patterns with locations, and never writes the author's experiences or renames titles.
---

# Review a series with Articulate

Use the Articulate tools exposed by the current host: `corpus_check`,
`title_workshop` and `restructure_plan`. Match tools by their Articulate server
and short name. Never invent a tool result when a tool is missing.

## Steps

1. Read each document the user names with the usual file tools. Pass them to
   `corpus_check` as `documents`, each with a `name` and its `text`. Pass any
   phrases the user repeats on purpose as `keep`.
2. Report each finding with its category, the documents and lines, the
   excerpt, the `reader_cost` and the `direction`. Keep the `scope`
   line beside the findings. Findings are report-only; none fails a build.
3. For titles, call `title_workshop` with the titles. Present each family and
   its question to the user and wait. Pass the user's own one-line answers back
   as `answers` before showing any suggestion, and label suggestions as
   suggestions.
4. When the user asks to move limit and source lines, call `restructure_plan`
   and show the diff. Apply it only when the user agrees, and only to the copy
   the user names.

## Rules

- Never write first-person experience, memories, opinions or reasons for the
  author. Where perspective is missing, say so and ask the author.
- Never rename a title or rewrite a heading without the user's choice.
- Keep every AI-assistance disclosure exactly as written.
- No finding here is evidence of who or what wrote a document.
