// Every MCP tool states its title and read/write hints. The Anthropic Software
// Directory Policy requires readOnlyHint, destructiveHint and title on every
// tool a listed server exposes.
import test from "node:test";
import assert from "node:assert/strict";
import { TOOLS, TOOL_ANNOTATIONS } from "../src/mcp.mjs";

const HINTS = ["readOnlyHint", "destructiveHint", "idempotentHint", "openWorldHint"];

test("every listed tool carries a title and boolean hints", () => {
  assert.deepEqual(new Set(TOOLS.map((t) => t.name)), new Set(Object.keys(TOOL_ANNOTATIONS)));
  for (const tool of TOOLS) {
    const notes = tool.annotations;
    assert.ok(notes.title && tool.title === notes.title, tool.name);
    for (const key of HINTS) assert.equal(typeof notes[key], "boolean", `${tool.name} ${key}`);
    assert.ok(tool.name.length <= 64);
    if (notes.readOnlyHint) assert.equal(notes.destructiveHint, false, tool.name);
  }
});

test("hints match what each tool does", () => {
  const by = Object.fromEntries(TOOLS.map((t) => [t.name, t.annotations]));
  assert.equal(by.learn_tutor_record.readOnlyHint, false);
  assert.equal(by.learn_tutor_plan.destructiveHint, true);
  for (const name of ["learn_tutor_due", "learn_tutor_studyplan", "learn_status", "learn_dry_run"]) {
    assert.equal(by[name].readOnlyHint, true, name);
  }
  assert.ok(Object.values(by).every((n) => n.openWorldHint === false));
});
