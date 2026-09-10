/** Local signed Bulletin handoff controls. No provider/model or production calls. */
import assert from "node:assert/strict";
import { mkdir, writeFile, readFile } from "node:fs/promises";
import { join, resolve, dirname } from "node:path";
import { pathToFileURL, fileURLToPath } from "node:url";
import { spawn, execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { startWorker } from "./bulletin_eval/worker_fixture.mjs";
import { feedControls } from "./bulletin_eval/feed_controls.mjs";
import { nextAction } from "./bulletin_eval/scripted_actor.mjs";

const args = Object.fromEntries(process.argv.slice(2).reduce((out, v, i, a) =>
  v.startsWith("--") ? [...out, [v.slice(2), a[i + 1]]] : out, []));
for (const key of ["bulletin", "dependencies", "out"]) {
  if (!args[key]) throw new Error(`--${key} is required`);
}
const sourceRoot = resolve(args.bulletin);
const sourceCommit = execFileSync("git", ["-C", sourceRoot, "rev-parse", "HEAD"], { encoding: "utf8", windowsHide: true }).trim();
assert.match(sourceCommit, /^[0-9a-f]{40}$/);
assert.equal(execFileSync("git", ["-C", sourceRoot, "status", "--porcelain", "--untracked-files=no"],
  { encoding: "utf8", windowsHide: true }).trim(), "", "Bulletin fixture source must be clean");
const out = resolve(args.out);
await mkdir(out); // Exclusive root: a previous run is never overwritten.
const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const componentFiles = ["harness/bulletin_task_contract.py", "harness/bulletin_observer.py",
  "harness/bulletin_task_review.py", "scripts/run_bulletin_task_check.py",
  "scripts/run_bulletin_evaluation_e2e.mjs", "scripts/bulletin_eval/worker_fixture.mjs",
  "scripts/bulletin_eval/scripted_actor.mjs", "scripts/bulletin_eval/feed_controls.mjs"];
const componentHashes = Object.fromEntries(await Promise.all(componentFiles.map(async path =>
  [path, createHash("sha256").update(await readFile(join(root, path))).digest("hex")])));
const fixture = await startWorker(sourceRoot, resolve(args.dependencies), join(out, "runtime"));
const results = [];
const save = (path, data) => writeFile(path, JSON.stringify(data, null, 2), { flag: "wx" });
async function python(argv) {
  return await new Promise((done, reject) => {
    const child = spawn(args.python ?? "python", argv, { cwd: root, windowsHide: true });
    let stdout = "", stderr = "";
    child.stdout.on("data", b => { stdout += b; });
    child.stderr.on("data", b => { stderr += b; });
    child.on("error", reject);
    child.on("close", code => done({ code, stdout, stderr }));
  });
}
try {
  process.argv.push("--base", fixture.base);
  const { makeAgent, send, build } = await import(pathToFileURL(join(sourceRoot, "scripts/smoke/client.mjs")));
  const variants = ["positive", "wrong_actor", "wrong_parent", "wrong_state",
    "wrong_task", "duplicate", "response_discarded", "nonce_transaction_rollback"];
  for (const variant of variants) {
    const a = await makeAgent(`eval-a-${variant}`);
    const b = await makeAgent(`eval-b-${variant}`);
    const task = `incident-${variant}`;
    const sourcePayload = { task_id: task, state: "reported" };
    const expected = { task_id: task, state: "needs_review" };
    const posted = await send(a, "POST", "/v1/posts", { room: "scratch", body: JSON.stringify(sourcePayload) });
    assert.equal(posted.status, 201);
    const sourceId = posted.body.post.id;
    const baseline = await (await fetch(`${fixture.base}/v1/feed?room=scratch&limit=100`)).json();
    assert.equal(baseline.next_before, null);
    const contract = {
      schema: "flywheel.bulletin-task-contract/v1", task_id: task,
      actor_a: a.thumbprint, actor_b: b.thumbprint, room: "scratch", source_id: sourceId,
      baseline_ids: baseline.posts.map(p => p.id), source_payload: sourcePayload,
      result_payload: expected, max_writes: 1, max_pages: 3, page_size: 100,
      max_response_bytes: 262144, request_timeout_seconds: 5,
    };
    const caseRoot = join(out, variant);
    await mkdir(caseRoot);
    // Seal outside acting inputs before constructing the potentially wrong reply.
    await save(join(caseRoot, "contract.json"), contract);
    const replyPayload = await nextAction(fixture.base, sourceId);
    if (variant === "wrong_state") replyPayload.state = "closed";
    if (variant === "wrong_task") replyPayload.task_id = "unrelated-task";
    const body = { room: "scratch", body: JSON.stringify(replyPayload) };
    if (variant !== "wrong_parent") body.parent_id = sourceId;
    const actor = variant === "wrong_actor" ? a : b;
    let transport;
    if (["response_discarded", "nonce_transaction_rollback"].includes(variant)) {
      if (variant === "nonce_transaction_rollback") {
        await fixture.db.exec("CREATE TRIGGER eval_nonce_fault BEFORE UPDATE ON spent_nonces WHEN NEW.result_kind = 'post' BEGIN SELECT RAISE(ABORT, 'isolated nonce result fault'); END;");
      }
      const request = await build(actor, "POST", "/v1/posts", body);
      const first = await fetch(request.url, request.init);
      const firstStatus = first.status;
      await first.arrayBuffer(); // Deliberately discard the accepted-post response body.
      const retry = await fetch(request.url, request.init);
      const replay = await retry.json();
      assert.equal(retry.status, 409);
      assert.equal(replay.code, "nonce_reused");
      assert.equal(Boolean(replay.applied), variant === "response_discarded");
      assert.equal(firstStatus, variant === "response_discarded" ? 201 : 500);
      if (variant === "nonce_transaction_rollback") await fixture.db.exec("DROP TRIGGER eval_nonce_fault;");
      transport = { attempted_requests: 2, observed_http_responses: 2,
        first_status: firstStatus, replay_status: retry.status,
        replay_has_applied_ref: Boolean(replay.applied),
        first_body_discarded: true, delivered_requests: null,
        limit: "Client discarded response body; not a simulated TCP disconnect." };
    } else {
      const reply = await send(actor, "POST", "/v1/posts", body);
      assert.equal(reply.status, 201);
      if (variant === "duplicate") assert.equal((await send(actor, "POST", "/v1/posts", body)).status, 201);
      transport = { attempted_requests: variant === "duplicate" ? 2 : 1,
        observed_http_responses: variant === "duplicate" ? 2 : 1,
        delivered_requests: null };
    }
    const run = await python(["scripts/run_bulletin_task_check.py", "--contract", join(caseRoot, "contract.json"),
      "--base", fixture.base, "--allow-loopback", "--out", caseRoot]);
    if (![0, 1, 3].includes(run.code)) throw new Error(run.stderr || run.stdout);
    const actual = JSON.parse(run.stdout);
    const expectPass = ["positive", "response_discarded"].includes(variant);
    assert.equal(actual.verdict, expectPass ? "PASS" : "FAIL", `${variant}: ${run.stdout}`);
    if (expectPass) assert.equal(actual.accepted_room_writes, 1);
    if (variant === "duplicate") assert.equal(actual.accepted_room_writes, 2);
    if (variant === "nonce_transaction_rollback") assert.equal(actual.accepted_room_writes, 0);
    results.push({ case: variant, expected: expectPass ? "PASS" : "FAIL", result: actual, transport });
    console.log(`${variant}: ${actual.verdict}, accepted room writes ${actual.accepted_room_writes}`);
  }
  const baselineReview = JSON.parse(await readFile(join(out, "positive/review.json"), "utf8"));
  baselineReview.observation.gaps = ["observer_restart", "sse_cursor_outside_replay_window"];
  await save(join(out, "missing-observation.json"), baselineReview.observation);
  const missing = await python(["scripts/run_bulletin_task_check.py", "--contract", join(out, "positive/contract.json"),
    "--observation", join(out, "missing-observation.json")]);
  assert.equal(missing.code, 3);
  results.push({ case: "missing_observation", expected: "UNVERIFIABLE", result: JSON.parse(missing.stdout),
    limit: "Explicit missing-coverage input; separate FeedRoom experiment tests actual replay loss." });
  const feed = await feedControls(fixture);
  console.log(`SSE: ${feed.unknown_cursor_returned_events}/55 replayed; ${feed.after_worker_restart_replayed_events} after restart`);
  await save(join(out, "results.json"), {
    schema: "flywheel.bulletin-e2e-controls/v1", cases: results,
    worker_bundle_sha256: fixture.bundleSha256, bulletin_source_commit: sourceCommit,
    flywheel_component_sha256: componentHashes, scripted_actors: true, feed,
    fault_injection: "Local D1 trigger aborts final nonce-result update; Worker source unchanged.",
    does_not_prove: ["Model behavior, general alignment, host containment, or complete activity observation."],
  });
} finally {
  await fixture.mf.dispose();
}
