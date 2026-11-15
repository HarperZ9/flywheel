// The browser entry: the tutor's practice, scheduling and diagnosis functions with no Node
// built-ins, so a static page can load them as ES modules with no bundler and no network.
// tests/learn-browser-entry.test.mjs walks this file's import graph and fails on any `node:`
// or bare specifier, and on any use of process, Buffer or require.
//
// What is left out: the hash-chained receipts (the ledger uses node:crypto), the session store
// (node:fs), the CLI, the MCP server and the run engine. A page keeps its own state.

export { newSession, newSessionWithFSRS, recordAttempt, recordAttemptWithGrade, mastery } from "./tutor/session.mjs";
export { reviewState, due } from "./tutor/schedule.mjs";
export { initializeItem, gradeAttempt, computeNextReview } from "./tutor/fsrs.mjs";
export { sortByRetrievability, selectNextItem } from "./tutor/itemscheduler.mjs";
export { misconceptions } from "./tutor/misconception.mjs";
export { diagnose, LEAVES } from "./tutor/diagnose.mjs";
export { interleave } from "./tutor/retrieval.mjs";
export {
  ITEM_SCHEMA, SET_SCHEMA, TOP_LEVELS, validateItem, validateItemSet, publicItem, diagnoseChoice,
} from "./tutor/choice.mjs";
