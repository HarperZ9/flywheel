#!/usr/bin/env node
// Smoke test for a packed tarball, run by ci.yml and release.yml on Windows, Linux and macOS.
//
//   node scripts/smoke-tarball.mjs <harperz9-learn-X.Y.Z.tgz> [--sums <SHA256SUMS>] [--static-only]
//
// --sums first checks the tarball against a sha256sum-format file. --static-only skips the runs.
// Static checks on the tarball's bytes: both bins start with #!/usr/bin/env node and a line
// feed, no text file carries a CR, package.json declares both bins, the vendored helper hashes to
// VENDORED.sha256, and no file names a local development path. Then it runs the package the way
// a person does, through `npx -y file:<tarball>`, from an empty folder with LEARN_HOME set and a
// private npm cache: `status` must print the envelope, `mcp` and `learn-mcp` must answer
// initialize, and the starting folder must stay empty. Last, the installed server must start
// from an absolute node with a PATH of system folders only. Exit 0 when every check passes.
// The file: prefix matters: given a bare path that exists, npx runs that file as the command
// instead of installing it as a package (npm exec's local-file lookup).
import { readFileSync, existsSync, mkdtempSync, mkdirSync, readdirSync, rmSync } from "node:fs";
import { gunzipSync } from "node:zlib";
import { createHash } from "node:crypto";
import { spawnSync } from "node:child_process";
import { tmpdir } from "node:os";
import { join, dirname, resolve, basename } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const TEXT = /\.(mjs|js|json|md|svg|html|txt)$/i;
const LOCAL = [/\b[A-Za-z]:[\\/]+dev[\\/]/i, /\/Users\/[A-Za-z]/, /\/home\/[a-z]/, /[A-Za-z]:[\\/]+Users[\\/]+[A-Za-z]/i];
const SHEBANG = "#!/usr/bin/env node\n";
const INIT = JSON.stringify({ jsonrpc: "2.0", id: 1, method: "initialize", params: {} }) + "\n";

// Minimal ustar reader: {name: Buffer} for every regular file, honouring pax path records.
export function untar(gz) {
  const buf = gunzipSync(gz);
  const files = {};
  let pax = null;
  for (let off = 0; off + 512 <= buf.length;) {
    const h = buf.subarray(off, off + 512);
    if (h.every((b) => b === 0)) break;
    const str = (a, b) => h.subarray(a, b).toString("utf8").replace(/\0.*$/s, "");
    const size = parseInt(str(124, 136).trim() || "0", 8);
    const type = String.fromCharCode(h[156] || 48);
    const prefix = str(345, 500);
    let name = prefix ? prefix + "/" + str(0, 100) : str(0, 100);
    const body = buf.subarray(off + 512, off + 512 + size);
    off += 512 + Math.ceil(size / 512) * 512;
    if (type === "x") {
      const m = body.toString("utf8").match(/\d+ path=([^\n]*)\n/);
      pax = m ? m[1] : null;
      continue;
    }
    if (pax) { name = pax; pax = null; }
    if (type === "0" || type === "\0") files[name] = Buffer.from(body);
  }
  return files;
}

function staticChecks(files) {
  const problems = [];
  const pkgBuf = files["package/package.json"];
  if (!pkgBuf) return { problems: ["package/package.json is missing"], pkg: null };
  const pkg = JSON.parse(pkgBuf.toString("utf8"));
  const want = { learn: "src/cli.mjs", "learn-mcp": "src/mcp.mjs" };
  if (JSON.stringify(pkg.bin) !== JSON.stringify(want)) problems.push(`package.json bin is ${JSON.stringify(pkg.bin)}`);
  for (const rel of Object.values(want)) {
    const b = files["package/" + rel];
    if (!b || !b.toString("utf8").startsWith(SHEBANG)) problems.push(`${rel} does not start with ${JSON.stringify(SHEBANG)}`);
  }
  for (const [name, b] of Object.entries(files)) {
    if (!TEXT.test(name)) continue;
    if (b.includes(13)) problems.push(`${name} carries a CR`);
    const text = b.toString("utf8");
    for (const re of LOCAL) if (re.test(text)) problems.push(`${name} names a local path (${re})`);
  }
  for (const line of readFileSync(join(ROOT, "VENDORED.sha256"), "utf8").split("\n").filter(Boolean)) {
    const [digest, rel] = line.trim().split(/\s+\*?/);
    const b = files["package/" + rel];
    const got = b ? createHash("sha256").update(b).digest("hex") : "missing";
    if (got !== digest) problems.push(`${rel} in the tarball hashes to ${got}, VENDORED.sha256 records ${digest}`);
  }
  return { problems, pkg };
}

// npx as argv: node plus npx-cli.js from the npm that ships beside this node.
function npx() {
  const nodeDir = dirname(process.execPath);
  const cli = [join(nodeDir, "node_modules", "npm", "bin", "npx-cli.js"),
    join(nodeDir, "..", "lib", "node_modules", "npm", "bin", "npx-cli.js")].find((p) => existsSync(p));
  if (!cli) throw new Error("npx-cli.js was not found beside this node");
  return [process.execPath, cli];
}

function findInstalled(cache) {
  const npxRoot = join(cache, "_npx");
  if (!existsSync(npxRoot)) return null;
  for (const d of readdirSync(npxRoot)) {
    const p = join(npxRoot, d, "node_modules", "@harperz9", "learn", "src", "mcp.mjs");
    if (existsSync(p)) return p;
  }
  return null;
}

function serverVersion(stdout) {
  const line = stdout.split("\n").find((l) => l.trim().startsWith("{"));
  return line ? JSON.parse(line).result?.serverInfo?.version : undefined;
}

function runChecks(tgz, version) {
  const problems = [];
  const base = mkdtempSync(join(tmpdir(), "learn-smoke-"));
  const cwd = join(base, "empty");
  const cache = join(base, "npm-cache");
  const state = join(base, "state");
  mkdirSync(cwd);
  const env = { ...process.env, LEARN_HOME: state, npm_config_cache: cache, npm_config_update_notifier: "false" };
  const [node, cli] = npx();
  const exec = (args, input) => spawnSync(node, [cli, ...args], { cwd, env, input, encoding: "utf8", timeout: 180000 });

  const spec = "file:" + tgz;
  const st = exec(["-y", spec, "status"]);
  let envelope = null;
  try { envelope = JSON.parse(st.stdout); } catch { /* reported below */ }
  if (st.status !== 0 || !envelope || envelope.tool !== "learn" || envelope.version !== version) {
    problems.push(`npx -y file:<tgz> status: exit ${st.status}, stdout ${JSON.stringify(st.stdout.slice(0, 200))}, stderr ${JSON.stringify((st.stderr || "").slice(0, 300))}`);
  }
  for (const [label, args] of [["npx -y file:<tgz> mcp", ["-y", spec, "mcp"]], ["npx -y --package file:<tgz> learn-mcp", ["-y", "--package", spec, "learn-mcp"]]]) {
    const r = exec(args, INIT);
    if (r.status !== 0 || serverVersion(r.stdout) !== version) {
      problems.push(`${label}: exit ${r.status}, stdout ${JSON.stringify(r.stdout.slice(0, 200))}, stderr ${JSON.stringify((r.stderr || "").slice(0, 300))}`);
    }
  }
  const left = readdirSync(cwd);
  if (left.length) problems.push(`the starting folder is not empty after the runs: ${left.join(", ")}`);

  const installed = findInstalled(cache);
  if (!installed) problems.push("the npx install of the tarball was not found in the private cache");
  else {
    const sysPath = process.platform === "win32" ? join(process.env.SystemRoot || "C:\\Windows", "System32") : "/usr/bin:/bin";
    const bare = { PATH: sysPath, LEARN_HOME: state };
    if (process.platform === "win32") bare.SystemRoot = process.env.SystemRoot;
    const r = spawnSync(process.execPath, [installed], { cwd, env: bare, input: INIT, encoding: "utf8", timeout: 60000 });
    if (r.status !== 0 || serverVersion(r.stdout) !== version) {
      problems.push(`absolute node, system-only PATH: exit ${r.status}, stderr ${JSON.stringify((r.stderr || "").slice(0, 300))}`);
    }
  }
  rmSync(base, { recursive: true, force: true });
  return problems;
}

function sumsCheck(tgz, sumsFile) {
  const bytes = readFileSync(tgz);
  const name = basename(tgz);
  const line = readFileSync(sumsFile, "utf8").split("\n").map((l) => l.trim().split(/\s+\*?/)).find(([, n]) => n === name);
  if (!line) return [`${sumsFile} has no line for ${name}`];
  const got = createHash("sha256").update(bytes).digest("hex");
  return got === line[0] ? [] : [`${name} hashes to ${got}, ${sumsFile} records ${line[0]}`];
}

function main(argv) {
  const flag = (f) => { const i = argv.indexOf(f); return i >= 0 ? argv[i + 1] : null; };
  const tgz = argv[0] && resolve(argv[0]);
  if (!tgz || !existsSync(tgz)) {
    console.error("usage: node scripts/smoke-tarball.mjs <harperz9-learn-X.Y.Z.tgz> [--sums <SHA256SUMS>] [--static-only]");
    return 2;
  }
  const sums = flag("--sums");
  const problems = sums ? sumsCheck(tgz, resolve(sums)) : [];
  const files = untar(readFileSync(tgz));
  const found = staticChecks(files);
  const pkg = found.pkg;
  problems.push(...found.problems);
  if (pkg && !argv.includes("--static-only")) problems.push(...runChecks(tgz, pkg.version));
  for (const p of problems) console.log("FAIL " + p);
  console.log(problems.length ? `smoke: ${problems.length} problem(s)` : `smoke: ok (${Object.keys(files).length} files, version ${pkg.version}, ${process.platform}, node ${process.version})`);
  return problems.length ? 1 : 0;
}

process.exitCode = main(process.argv.slice(2));
