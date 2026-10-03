import { test } from "node:test";
import assert from "node:assert/strict";
import { boot, HOLD_RUN, PASS_RUN } from "./setup.mjs";
import { rederive } from "../scripts/rederive.mjs";

// A transcript in Claude Code's JSONL shape: assistant rows carry tool_use
// blocks, user rows carry tool_result blocks.
function transcript(rows) {
  return rows.map((r) => JSON.stringify(r)).join("\n") + "\n";
}
const use = (id, name, input) => ({ type: "assistant", message: { role: "assistant", content: [{ type: "tool_use", id, name, input }] } });
const result = (id, content, isError = false) => ({ type: "user", message: { role: "user", content: [{ type: "tool_result", tool_use_id: id, content, is_error: isError }] } });

async function session() {
  const b = await boot({ monitor: (argv, init) => (JSON.parse(init.stdin).tool_input.command === "rm -rf build" ? HOLD_RUN : PASS_RUN) });
  const held = await b.toolCall({ tool: "Bash", tool_use_id: "toolu_a", command: "rm -rf build" });
  await b.toolCall({ tool: "Bash", tool_use_id: "toolu_b", command: "git push origin main" });
  await b.turnComplete();
  return { receipts: b.fs.files.get("/work/.flywheel/mod-receipts/sess-1.jsonl"), denyText: held.value.deny };
}

test("receipts re-derive from the transcript: MATCH", async () => {
  const { receipts, denyText } = await session();
  const t = transcript([
    use("toolu_a", "Bash", { command: "rm -rf build" }), result("toolu_a", denyText, true),
    use("toolu_b", "Bash", { command: "git push origin main" }), result("toolu_b", [{ type: "text", text: "Everything up-to-date" }]),
  ]);
  const report = await rederive(receipts, t);
  assert.equal(report.verdict, "MATCH");
  assert.equal(report.calls, 2);
  assert.deepEqual(report.problems, []);
  assert.deepEqual(report.unreceipted, []);
});

test("a call rewritten before the mod saw it shows as DRIFT on input-digest", async () => {
  const { receipts, denyText } = await session();
  const t = transcript([
    use("toolu_a", "Bash", { command: "rm -rf build" }), result("toolu_a", denyText, true),
    use("toolu_b", "Bash", { command: "git push --force origin main" }), result("toolu_b", "ok"),
  ]);
  const report = await rederive(receipts, t);
  assert.equal(report.verdict, "DRIFT");
  assert.deepEqual(report.problems.map((p) => [p.kind, p.tool_use_id]), [["input-digest", "toolu_b"]]);
});

test("a receipt that says passed while the transcript shows a hold is DRIFT, and so is a missing call", async () => {
  const { receipts, denyText } = await session();
  const t = transcript([
    use("toolu_a", "Bash", { command: "rm -rf build" }), result("toolu_a", "removed", false),
    use("toolu_c", "Bash", { command: "ls" }), result("toolu_c", denyText, true),
  ]);
  const report = await rederive(receipts, t);
  assert.deepEqual(report.problems.map((p) => p.kind).sort(), ["decision", "missing-in-transcript"]);
  assert.deepEqual(report.unreceipted, ["toolu_c"]);
});

test("an edited receipt line breaks the chain", async () => {
  const { receipts, denyText } = await session();
  const forged = receipts.replace('"decision":"held"', '"decision":"pass"');
  const t = transcript([use("toolu_a", "Bash", { command: "rm -rf build" }), result("toolu_a", denyText, true),
    use("toolu_b", "Bash", { command: "git push origin main" }), result("toolu_b", "ok")]);
  const report = await rederive(forged, t);
  assert.equal(report.verdict, "DRIFT");
  assert.ok(report.problems.some((p) => p.kind === "chain"));
});
