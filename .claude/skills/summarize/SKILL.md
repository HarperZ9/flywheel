---
name: summarize
description: Answer the four end-of-work questions for the current stretch of work. Use when the user asks to summarize, wrap up, hand off, check in, or report status on a task, a goal, or a session, and use it before a handoff or a compaction.
user-invocable: true
argument-hint: "[task|goal|session] [--strict]"
---

# /summarize: the four questions, with the facts derived

Answer these, in this order, and nothing else:

1. What did we set out to do?
2. What did we do?
3. What is left to finish this work?
4. What decisions are needed from the operator?

The point is not the prose. A summary written entirely by the agent that did
the work is a claim about a claim. So the factual half comes from the
repository, and your half is labelled as assertion.

## Workflow

1. Pick the scope. `task` is the last commit plus the working tree, for one
   unit of work. `goal` is the whole branch against its base. `session` adds
   receipts written during the session. Default to `task` after a single piece
   of work and `session` at the end of a long stretch. Say which you chose.

2. Get the derived half. From a flywheel checkout:

   ```bash
   python scripts/run_session_summary.py --scope task --out "" --markdown-out ""
   ```

   Outside flywheel, set `FLYWHEEL_REPO` and run `flywheel session-summary
   --scope task`, or fall back to `git status --porcelain`, `git log`, and
   `git rev-list --left-right --count @{u}...HEAD` and derive the same facts by
   hand. The command reads git only. It writes nothing to the tree.

3. Read the `derived` list under each answer. These are facts. Do not restate
   them one by one in your reply, and do not contradict them.

4. Write the `stated` half: intent, what the work was FOR, the judgement calls,
   the decisions only the operator can make. Feed them back so the tool can
   check them:

   ```bash
   python scripts/run_session_summary.py --scope task --intent "..." --remaining "..." --decision "..."
   ```

   Passing an empty `--remaining ""` is how you claim nothing is left. If the
   tree disagrees the verdict comes back `SUMMARY_DISAGREES` and names the
   contradiction. Fix your claim, not the check.

5. With `--strict`, add `--fail-on-disagreement` and report the non-zero exit
   as a finding rather than smoothing it over.

## Writing the answer

Follow the operator's standing prose rules. Technical style english. No
em-dashes. No throat-clearing opener, no landing sentence, no rule of three,
no corrective negation, no performed enthusiasm. Vary sentence length.

Specific to this skill:

- Question 2 is what CHANGED, not what you attempted. Name files and commands.
  A test that failed is part of the answer, with its output.
- Question 3 is work, not aspiration. "Push the branch" is remaining work.
  "Consider adding caching" is not.
- Question 4 lists only decisions you genuinely cannot make. If you can pick a
  sensible default, pick it and say you did. An empty question 4 is a good
  outcome, and writing "none" is the right answer when it is true.
- Keep honest nulls. Untested, unverified, and unknown all survive into the
  summary. Never upgrade "it ran" to "it works".
- No local paths in anything the operator might forward.

Length: four short sections. If a section needs more than five bullets the
scope was too wide, so say that and narrow it.
