import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { main } from "../src/cli.mjs";

test("run halts at assess, resume completes, verify ok, receipt written", async () => {
  const dir = mkdtempSync(join(tmpdir(), "learn-"));
  const wfPath = join(dir, "wf.json");
  writeFileSync(wfPath, JSON.stringify({ adapter: "fake", course: "intro",
    steps: [{ kind: "navigate", target: "x" }, { kind: "assess", label: "quiz" }, { kind: "complete" }] }));
  const r1 = await main(["run", wfPath, "--id", "run1"], { dir });
  assert.match(r1.out, /halted-assess/);
  const r2 = await main(["resume", "run1", "--attest", "did quiz"], { dir });
  assert.match(r2.out, /completed/);
  const v = await main(["verify", "run1"], { dir });
  assert.match(v.out, /chain ok/i);
  const rc = await main(["receipt", "run1"], { dir });
  assert.match(rc.out, /receipt written/i);
});
