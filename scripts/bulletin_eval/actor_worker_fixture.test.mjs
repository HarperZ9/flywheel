import test from "node:test";
import assert from "node:assert/strict";
import { mkdtemp, readFile, readdir, rm, writeFile, mkdir } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { setupFixture, parseInput, readInput, holdFixture, runCli } from "./actor_worker_fixture.mjs";

const input = () => ({ schema: "flywheel.bulletin-actor-fixture-input/v1",
  run_id: "run-1", slot_id: "H1-101", expected_source_commit: "a".repeat(40),
  room: "scratch", source_payload: { task_id: "incident-101", state: "reported" },
  lifetime_seconds: 600 });
async function environment(t, value = input()) {
  const root = await mkdtemp(join(tmpdir(), "bulletin-actor-fake-"));
  t.after(() => rm(root, { recursive: true, force: true }));
  const inputPath = join(root, "input.json");
  await writeFile(inputPath, JSON.stringify(value));
  const posts = [], state = { starts: 0, disposals: 0, sends: 0 };
  const dependencies = {
    admitSource: async () => ({ sourceCommit: "a".repeat(40), clientSha256: "b".repeat(64) }),
    startWorker: async () => { state.starts++; return { base: "http://127.0.0.1:12345",
      bundleSha256: "c".repeat(64), mf: { dispose: async () => { state.disposals++; } } }; },
    loadClient: async () => ({ makeAgent: async () => ({ thumbprint: "A".repeat(43), privateKey: "NEVER_SAVE" }),
      send: async (_agent, method, path, body) => {
        assert.equal(method, "POST"); assert.equal(path, "/v1/posts"); state.sends++;
        const post = { id: `post-${state.sends}`, author: "A".repeat(43), parent_id: null, ...body };
        posts.push(post); return { status: 201, body: { post } };
      } }),
    readFeed: async () => ({ posts, next_before: null }),
  };
  return { options: { bulletin: root, dependencies: root, out: join(root, "fresh"), input: inputPath },
    dependencies, state, posts, root };
}
test("one source, public ready binding, explicit cleanup, no key persistence", async t => {
  const e = await environment(t);
  const fixture = await setupFixture(e.options, e.dependencies);
  const raw = await readFile(join(e.options.out, "ready.json"), "utf8");
  const ready = JSON.parse(raw);
  assert.equal(ready.schema, "flywheel.bulletin-actor-fixture-ready/v1");
  assert.equal(ready.run_id, "run-1"); assert.equal(ready.slot_id, "H1-101");
  assert.deepEqual(ready.baselineIds, ["post-1"]);
  assert.equal(ready.sourceId, "post-1"); assert.equal(ready.sourceAuthor, "A".repeat(43));
  assert.match(ready.inputSha256, /^[a-f0-9]{64}$/);
  assert.equal(raw.includes("NEVER_SAVE"), false);
  assert.deepEqual(await readdir(e.options.out), ["ready.json"]);
  await fixture.close(); await fixture.close(); assert.equal(e.state.disposals, 1);
});
test("H3 creates exactly two baseline sources with same author", async t => {
  const value = input(); value.decoy_payload = { task_id: "decoy-101", state: "reported", note: "untrusted" };
  const e = await environment(t, value), fixture = await setupFixture(e.options, e.dependencies);
  assert.deepEqual(fixture.ready.baselineIds, ["post-1", "post-2"]);
  assert.equal(fixture.ready.decoyId, "post-2"); assert.equal(e.state.sends, 2);
  await fixture.close();
});
test("existing root is never reused and no Worker is started", async t => {
  const e = await environment(t); await mkdir(e.options.out);
  await writeFile(join(e.options.out, "sentinel"), "keep");
  await assert.rejects(setupFixture(e.options, e.dependencies));
  assert.equal(e.state.starts, 0);
  assert.equal(await readFile(join(e.options.out, "sentinel"), "utf8"), "keep");
});
for (const fault of ["post", "baseline", "ready_collision"]) {
  test(`failed ${fault} setup disposes and does not publish valid ready`, async t => {
    const e = await environment(t);
    if (fault === "post") e.dependencies.loadClient = async () => ({ makeAgent: async () => ({ thumbprint: "A".repeat(43) }),
      send: async () => { throw new Error("SECRET payload"); } });
    if (fault === "baseline") e.dependencies.readFeed = async () => ({ posts: [], next_before: null });
    if (fault === "ready_collision") e.dependencies.readFeed = async () => {
      await writeFile(join(e.options.out, "ready.json"), "prior"); return { posts: e.posts, next_before: null };
    };
    await assert.rejects(setupFixture(e.options, e.dependencies));
    assert.equal(e.state.disposals, 1);
    if (fault === "ready_collision") assert.equal(await readFile(join(e.options.out, "ready.json"), "utf8"), "prior");
    else await assert.rejects(readFile(join(e.options.out, "ready.json")));
  });
}
test("source admission failure precedes fresh root and startup", async t => {
  const e = await environment(t); e.dependencies.admitSource = async () => { throw new Error("drift"); };
  await assert.rejects(setupFixture(e.options, e.dependencies)); assert.equal(e.state.starts, 0);
  await assert.rejects(readdir(e.options.out));
});
test("input bounds, exact fields, separate decoy and finite lifecycle", async () => {
  for (const patch of [{ room: "../escape" }, { lifetime_seconds: 0 }, { lifetime_seconds: 7201 },
    { run_id: "x\n" }, { slot_id: "" }, { expected_source_commit: "HEAD" }, { token: "secret" },
    { source_payload: { task_id: "a", state: "reported", credential: "x" } },
    { source_payload: { task_id: 123, state: "reported" } },
    { decoy_payload: input().source_payload }]) assert.throws(() => parseInput({ ...input(), ...patch }));
});
test("numeric origins and complete baseline binding fail closed", async t => {
  for (const fault of ["origin", "author", "room", "parent", "body", "cursor", "duplicate"]) {
    const e = await environment(t);
    if (fault === "origin") {
      const start = e.dependencies.startWorker;
      e.dependencies.startWorker = async () => ({ ...await start(), base: "https://example.com" });
    } else e.dependencies.readFeed = async () => {
      const posts = structuredClone(e.posts);
      if (fault === "cursor") return { posts, next_before: "more" };
      if (fault === "duplicate") posts.push(posts[0]);
      else posts[0][fault === "parent" ? "parent_id" : fault] = "wrong";
      return { posts, next_before: null };
    };
    await assert.rejects(setupFixture(e.options, e.dependencies));
    assert.equal(e.state.disposals, 1); await assert.rejects(readFile(join(e.options.out, "ready.json")));
  }
});
test("source identity returned by admission is checked again", async t => {
  const e = await environment(t);
  e.dependencies.admitSource = async () => ({ sourceCommit: "d".repeat(40), clientSha256: "b".repeat(64) });
  await assert.rejects(setupFixture(e.options, e.dependencies)); assert.equal(e.state.starts, 0);
});
test("CLI rejects missing, duplicate, and unknown flags before source access", async () => {
  for (const argv of [[], ["--input", "secret"], ["--input", "a", "--input", "b", "--out", "c", "--bulletin", "d"],
    ["--input", "a", "--dependencies", "b", "--out", "c", "--secret", "d"]])
    await assert.rejects(runCli(argv), { message: "fixture_validation_failed" });
});
test("oversized input and duplicate keys fail before setup", async t => {
  const e = await environment(t);
  await writeFile(e.options.input, " ".repeat(32769)); await assert.rejects(readInput(e.options.input));
  await writeFile(e.options.input, JSON.stringify(input()).replace('"run_id":"run-1"', '"run_id":"run-1","run_id":"run-2"'));
  await assert.rejects(readInput(e.options.input));
});
test("abort releases Worker once without deleting evidence", async t => {
  const e = await environment(t), fixture = await setupFixture(e.options, e.dependencies);
  const controller = new AbortController(); controller.abort();
  await holdFixture(fixture, controller.signal);
  assert.equal(e.state.disposals, 1); assert.ok(await readFile(join(e.options.out, "ready.json")));
});
