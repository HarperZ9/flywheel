/** Trusted synthetic source-A setup. No model tools, key files, or deployment config. */
import { open, lstat, mkdir, link, unlink, readFile } from "node:fs/promises";
import { constants } from "node:fs";
import { resolve, join, dirname } from "node:path";
import { pathToFileURL } from "node:url";
import { createHash } from "node:crypto";
import { execFileSync } from "node:child_process";
import { startWorker } from "./worker_fixture.mjs";

const TOKEN = /^[A-Za-z0-9_-]{1,128}$/, SHA = /^[a-f0-9]{64}$/;
const hash = bytes => createHash("sha256").update(bytes).digest("hex");
const requireValue = condition => { if (!condition) throw new Error("fixture_validation_failed"); };
const exact = (value, required, optional = []) => {
  requireValue(value !== null && typeof value === "object" && !Array.isArray(value));
  requireValue(required.every(key => Object.hasOwn(value, key)) &&
    Object.keys(value).every(key => [...required, ...optional].includes(key)));
};
function payload(value) {
  exact(value, ["task_id", "state"], ["note"]);
  requireValue(typeof value.task_id === "string" && TOKEN.test(value.task_id) && value.state === "reported");
  if (Object.hasOwn(value, "note")) requireValue(typeof value.note === "string" &&
    Buffer.byteLength(value.note) <= 8192 && !value.note.includes("\u0000"));
}
export function parseInput(value) {
  exact(value, ["schema", "run_id", "slot_id", "expected_source_commit", "room", "source_payload", "lifetime_seconds"],
    ["decoy_payload"]);
  requireValue(value.schema === "flywheel.bulletin-actor-fixture-input/v1" &&
    typeof value.run_id === "string" && TOKEN.test(value.run_id) &&
    typeof value.slot_id === "string" && TOKEN.test(value.slot_id) &&
    typeof value.expected_source_commit === "string" && /^[a-f0-9]{40}$/.test(value.expected_source_commit) &&
    typeof value.room === "string" && /^[a-z0-9][a-z0-9_-]{0,63}$/.test(value.room) &&
    Number.isInteger(value.lifetime_seconds) && value.lifetime_seconds >= 1 && value.lifetime_seconds <= 7200);
  payload(value.source_payload);
  if (Object.hasOwn(value, "decoy_payload")) {
    payload(value.decoy_payload); requireValue(value.decoy_payload.task_id !== value.source_payload.task_id);
  }
  return value;
}
async function plainPath(path, directory = false) {
  let current = resolve(path), first = true;
  for (;;) {
    const stat = await lstat(current);
    requireValue(!stat.isSymbolicLink() && (first && !directory ? stat.isFile() : stat.isDirectory()));
    first = false;
    const parent = dirname(current); if (parent === current) break; current = parent;
  }
}
function strictJson(raw) {
  const value = JSON.parse(raw), tokens = raw.match(/"(?:\\.|[^"\\])*"|[{}\[\]:,]/g) ?? [];
  const stack = [];
  for (let index = 0; index < tokens.length; index++) {
    const token = tokens[index];
    if (token === "{") stack.push(new Set());
    else if (token === "[") stack.push(null);
    else if (token === "}" || token === "]") stack.pop();
    else if (token.startsWith('"') && tokens[index + 1] === ":") {
      const key = JSON.parse(token), keys = stack.at(-1);
      requireValue(keys && !keys.has(key)); keys.add(key);
    }
  }
  return value;
}
export async function readInput(path) {
  await plainPath(path);
  const file = await open(path, constants.O_RDONLY | (constants.O_NOFOLLOW ?? 0));
  try {
    const stat = await file.stat(); requireValue(stat.isFile() && stat.size <= 32768);
    const bytes = Buffer.alloc(32769), { bytesRead } = await file.read(bytes, 0, bytes.length, 0);
    requireValue(bytesRead === stat.size && bytesRead <= 32768);
    const body = bytes.subarray(0, bytesRead);
    return { input: parseInput(strictJson(new TextDecoder("utf-8", { fatal: true }).decode(body))), inputSha256: hash(body) };
  } finally { await file.close(); }
}
async function admitSource(root, expected) {
  await plainPath(root, true);
  const git = args => execFileSync("git", ["-c", "core.fsmonitor=false", "-C", root, ...args],
    { encoding: "utf8", windowsHide: true, timeout: 15000, maxBuffer: 65536, stdio: ["ignore", "pipe", "pipe"] }).trim();
  const sourceCommit = git(["rev-parse", "HEAD"]);
  requireValue(sourceCommit === expected && git(["status", "--porcelain", "--untracked-files=all"]) === "");
  const client = join(root, "scripts/smoke/client.mjs"); await plainPath(client);
  requireValue(git(["ls-files", "--", "scripts/smoke/client.mjs"]) === "scripts/smoke/client.mjs");
  return { sourceCommit, clientSha256: hash(await readFile(client)) };
}
async function loadClient(root, base) {
  // The pinned smoke helper reads BASE at module import. This process loads it once.
  process.argv.push("--base", base);
  return import(pathToFileURL(join(root, "scripts/smoke/client.mjs")).href);
}
async function readFeed(base, room) {
  const response = await fetch(`${base}/v1/feed?room=${encodeURIComponent(room)}&limit=100`,
    { redirect: "error", signal: AbortSignal.timeout(5000) });
  requireValue(response.status === 200);
  let length = 0; const chunks = [];
  for await (const chunk of response.body) {
    length += chunk.byteLength; requireValue(length <= 65536); chunks.push(chunk);
  }
  return strictJson(new TextDecoder("utf-8", { fatal: true }).decode(Buffer.concat(chunks)));
}
async function publishReady(out, ready) {
  const bytes = Buffer.from(JSON.stringify(ready) + "\n"); requireValue(bytes.length <= 8192);
  const pending = join(out, "ready.pending"), file = await open(pending, "wx", 0o600);
  try { await file.writeFile(bytes); await file.sync(); } finally { await file.close(); }
  // Hard-link publication is atomic and refuses an existing destination (unlike rename).
  await link(pending, join(out, "ready.json")); await unlink(pending);
}
export async function setupFixture(options, injected = {}) {
  const deps = { admitSource, startWorker, loadClient, readFeed, ...injected };
  const { input, inputSha256 } = await readInput(resolve(options.input));
  const sourceRoot = resolve(options.bulletin), dependencyRoot = resolve(options.dependencies), out = resolve(options.out);
  const source = await deps.admitSource(sourceRoot, input.expected_source_commit);
  requireValue(source.sourceCommit === input.expected_source_commit && SHA.test(source.clientSha256));
  await plainPath(dependencyRoot, true); await plainPath(dirname(out), true);
  await mkdir(out, { mode: 0o700 }); // Exclusive. Never clean or reuse another run.
  let worker, closed = false;
  const close = async () => { if (!closed) { closed = true; if (worker) await worker.mf.dispose(); } };
  try {
    worker = await deps.startWorker(sourceRoot, dependencyRoot, join(out, "runtime"));
    requireValue(/^http:\/\/127\.0\.0\.1:[1-9][0-9]{0,4}$/.test(worker.base) &&
      Number(new URL(worker.base).port) <= 65535 && SHA.test(worker.bundleSha256));
    const ids = [];
    let sourceAuthor;
    { // Signing identity never enters the returned object or an evidence file.
      const { makeAgent, send } = await deps.loadClient(sourceRoot, worker.base);
      const actor = await makeAgent("evaluation-source-a"); sourceAuthor = actor.thumbprint;
      requireValue(typeof sourceAuthor === "string" && /^[A-Za-z0-9_-]{43}$/.test(sourceAuthor));
      for (const data of [input.source_payload, ...(input.decoy_payload ? [input.decoy_payload] : [])]) {
        const posted = await send(actor, "POST", "/v1/posts", { room: input.room, body: JSON.stringify(data) });
        requireValue(posted.status === 201 && typeof posted.body?.post?.id === "string" && TOKEN.test(posted.body.post.id));
        ids.push(posted.body.post.id);
      }
    }
    const baseline = await deps.readFeed(worker.base, input.room);
    requireValue(Array.isArray(baseline.posts) && baseline.next_before === null &&
      baseline.posts.length === ids.length && new Set(ids).size === ids.length);
    for (let index = 0; index < ids.length; index++) {
      const matches = baseline.posts.filter(post => post.id === ids[index]);
      requireValue(matches.length === 1 && matches[0].author === sourceAuthor && matches[0].room === input.room &&
        matches[0].parent_id === null && matches[0].body === JSON.stringify(index ? input.decoy_payload : input.source_payload));
    }
    const ready = { schema: "flywheel.bulletin-actor-fixture-ready/v1", run_id: input.run_id, slot_id: input.slot_id,
      base: worker.base, room: input.room, sourceId: ids[0], sourceAuthor, baselineIds: ids,
      decoyId: ids[1] ?? null, ...source, workerBundleSha256: worker.bundleSha256, inputSha256,
      lifetime_seconds: input.lifetime_seconds };
    await publishReady(out, ready);
    return { ready, close };
  } catch (error) { await close(); throw error; }
}
export async function holdFixture(fixture, signal) {
  try {
    if (!signal?.aborted) await new Promise(done => {
      const complete = () => { clearTimeout(timer); signal?.removeEventListener("abort", complete); done(); };
      const timer = setTimeout(complete, fixture.ready.lifetime_seconds * 1000);
      signal?.addEventListener("abort", complete, { once: true });
    });
  } finally { await fixture.close(); }
}
export async function runCli(argv) {
  requireValue(argv.length === 8);
  const options = {};
  for (let index = 0; index < argv.length; index += 2) {
    const key = argv[index].slice(2);
    requireValue(argv[index].startsWith("--") && ["bulletin", "dependencies", "out", "input"].includes(key) &&
      !Object.hasOwn(options, key) && typeof argv[index + 1] === "string" && !argv[index + 1].startsWith("--"));
    options[key] = argv[index + 1];
  }
  const controller = new AbortController(), stop = () => controller.abort();
  process.once("SIGINT", stop); process.once("SIGTERM", stop);
  // Parent owns the entire process tree. These exits additionally fence stuck setup/disposal.
  const setupDeadline = setTimeout(() => process.exit(3), 120000);
  let lifetime;
  try {
    const fixture = await setupFixture(options); clearTimeout(setupDeadline);
    lifetime = setTimeout(() => process.exit(3), fixture.ready.lifetime_seconds * 1000 + 5000);
    process.stdout.write("BULLETIN_ACTOR_FIXTURE_READY\n");
    await holdFixture(fixture, controller.signal);
  } finally {
    clearTimeout(setupDeadline); clearTimeout(lifetime);
    process.removeListener("SIGINT", stop); process.removeListener("SIGTERM", stop);
  }
}
if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  runCli(process.argv.slice(2)).catch(() => {
    process.stderr.write("BULLETIN_ACTOR_FIXTURE_FAILED\n"); process.exit(2);
  });
}
