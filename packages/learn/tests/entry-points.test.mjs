// The package's own entry points. In 1.6.0 the `learn` bin had no #!/usr/bin/env node
// line and shipped with CRLF endings, so npm's Windows shim ran the .mjs file itself and printed
// nothing, and Linux ran it as a shell script. Main-module detection compared strings, so a
// linked bin was never treated as the program. There was no MCP bin and no `learn mcp`.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, readdirSync, statSync, mkdtempSync, symlinkSync, cpSync, chmodSync, mkdirSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, dirname, relative } from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const SRC = join(ROOT, "src");
const read = (rel) => readFileSync(join(ROOT, rel), "utf8");
const tmp = () => mkdtempSync(join(tmpdir(), "learn-entry-"));
const INIT = JSON.stringify({ jsonrpc: "2.0", id: 1, method: "initialize", params: {} }) + "\n";

function run(file, args, { input, env = {}, cwd } = {}) {
  return spawnSync(file, args, { input, cwd, encoding: "utf8", timeout: 30000, env: { ...process.env, LEARN_HOME: tmp(), ...env } });
}

function linkedSrc() {
  const link = join(tmp(), "linked");
  symlinkSync(SRC, link, process.platform === "win32" ? "junction" : "dir");
  return link;
}

test("both bins start with #!/usr/bin/env node and a line feed", () => {
  for (const rel of ["src/cli.mjs", "src/mcp.mjs"]) {
    assert.ok(read(rel).startsWith("#!/usr/bin/env node\n"), rel);
  }
});

test("package.json declares the learn and learn-mcp bins", () => {
  const pkg = JSON.parse(read("package.json"));
  assert.deepEqual(pkg.bin, { learn: "src/cli.mjs", "learn-mcp": "src/mcp.mjs" });
});

test(".gitattributes checks every text file out with LF, and no shipped file carries a CR", () => {
  assert.match(read(".gitattributes"), /^\*\s+text=auto\s+eol=lf\s*$/m);
  const pkg = JSON.parse(read("package.json"));
  const files = [join(ROOT, "package.json")];
  const walk = (p) => { if (statSync(p).isDirectory()) readdirSync(p).forEach((n) => walk(join(p, n))); else files.push(p); };
  pkg.files.forEach((f) => walk(join(ROOT, f)));
  const withCR = files.filter((f) => /\.(mjs|js|json|md|svg|html)$/.test(f) && readFileSync(f).includes(13));
  assert.deepEqual(withCR.map((f) => relative(ROOT, f)), []);
});

test("the CLI runs when started through a linked folder, as npm links bins", () => {
  const r = run(process.execPath, [join(linkedSrc(), "cli.mjs"), "status"]);
  assert.equal(r.status, 0, r.stderr);
  assert.equal(JSON.parse(r.stdout).tool, "learn");
});

test("the MCP server runs when started through a linked folder", () => {
  const r = run(process.execPath, [join(linkedSrc(), "mcp.mjs")], { input: INIT });
  assert.equal(r.status, 0, r.stderr);
  assert.equal(JSON.parse(r.stdout.split("\n")[0]).result.serverInfo.name, "learn");
});

test("`learn mcp` serves MCP on stdio, writes nothing else to stdout and exits when stdin closes", () => {
  const r = run(process.execPath, [join(SRC, "cli.mjs"), "mcp"], { input: INIT });
  assert.equal(r.status, 0, r.stderr);
  assert.equal(r.stderr, "");
  const lines = r.stdout.split("\n").filter(Boolean);
  assert.equal(lines.length, 1);
  assert.equal(JSON.parse(lines[0]).result.serverInfo.name, "learn");
});

test("the usage line names the mcp subcommand", async () => {
  const { main } = await import("../src/cli.mjs");
  assert.match((await main([], { dir: tmp() })).out, /\|mcp>/);
});

test("with an absolute node and a PATH of system folders only, the MCP server still starts", () => {
  const sys = process.platform === "win32" ? join(process.env.SystemRoot || "C:\\Windows", "System32") : "/usr/bin:/bin";
  const env = { PATH: sys, LEARN_HOME: tmp() };
  if (process.platform === "win32") env.SystemRoot = process.env.SystemRoot;
  const r = spawnSync(process.execPath, [join(SRC, "mcp.mjs")], { input: INIT, env, encoding: "utf8", timeout: 30000 });
  assert.equal(r.status, 0, r.stderr);
  assert.equal(JSON.parse(r.stdout.split("\n")[0]).result.serverInfo.name, "learn");
});

test("on Linux and macOS a linked, executable cli.mjs runs as a program, as an npm bin does", (t) => {
  if (process.platform === "win32") return t.skip("npm runs bins through a .cmd shim on Windows");
  const pkg = join(tmp(), "pkg");
  cpSync(SRC, join(pkg, "src"), { recursive: true });
  cpSync(join(ROOT, "package.json"), join(pkg, "package.json"));
  chmodSync(join(pkg, "src", "cli.mjs"), 0o755);
  const bin = join(tmp(), "bin");
  mkdirSync(bin);
  symlinkSync(join(pkg, "src", "cli.mjs"), join(bin, "learn"));
  const r = run(join(bin, "learn"), ["status"]);
  assert.equal(r.status, 0, r.stderr);
  assert.equal(JSON.parse(r.stdout).tool, "learn");
});
