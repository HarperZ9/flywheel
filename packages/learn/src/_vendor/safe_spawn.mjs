// Start a child program without handing it the caller's folder or environment.
//
// Node port of safe_spawn.py with the same rules; vendored verbatim, and the
// conformance kit compares the copy's SHA-256 with the canonical one, so
// per-tool choices are arguments, never edits. Every start resolves the
// executable to an absolute path (an override variable must hold one; a PATH
// walk skips relative entries and entries that reach a working folder, and on
// Windows a .exe anywhere beats a batch shim; a bare name holding ":" is
// refused), runs in a new private empty folder unless the caller names one,
// passes an environment allowlist whose PATH keeps what the walk keeps (on
// POSIX, /bin:/usr/bin when that leaves nothing, since an empty PATH means the
// current folder there), plus NoDefaultCurrentDirectoryInExePath=1 on Windows,
// refuses cmd.exe metacharacters in any argument to a .cmd or .bat target, adds
// -P and PYTHONSAFEPATH=1 for a Python target (3.11 or later), and adds the
// named CLI profile's flags; an unproven profile needs a grant naming it.
// Messages never print a resolved path, an argument or a value.
// The working folders are the caller's current folder and the folder named for
// the child. An entry reaches one when, resolved through links, it is that
// folder or lies below it, by name or by file identity; on a filesystem without
// file indices, any folder on the working folder's device counts. A filesystem
// root or a folder holding the home folder counts only as itself. The running
// node's folder and, on Windows, the Windows, System32 and SysWOW64 folders
// always stay, and a working folder that is one of them guards nothing: the
// caller already runs code from there. Each kept entry becomes its real folder,
// so a link repointed after the check cannot change what starts. Windows PATH is
// read as cmd.exe reads it, and an entry whose folder holds the PATH separator
// leaves: programs disagree on it.
// Node refuses to start a .cmd or .bat file without a shell (CVE-2024-27980),
// so a batch target starts through %SystemRoot%\System32\cmd.exe with
// /d /v:off /s /c and every argument quoted. The refusal rules match the Python
// helper exactly, which also refuses ")" where Python would leave it unquoted.
import { spawn, spawnSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

export const SAFE_SPAWN_VERSION = "1.0.1";
export const POSIX_FALLBACK_PATH = "/bin:/usr/bin";
export const BATCH_SUFFIXES = [".cmd", ".bat"];
const STARTABLE = [".com", ".exe", ...BATCH_SUFFIXES];
export const CMD_UNSAFE = new Set(['"', "%", "^", "&", "|", "<", ">", "!", "\r", "\n"]);
export const CMD_UNSAFE_UNQUOTED = new Set([")"]);
export const NO_CWD_SEARCH = "NoDefaultCurrentDirectoryInExePath";
const DRAIN_MS = 5000;
export const WINDOWS_BASE_ENV = [
  "PATH", "PATHEXT", "SYSTEMROOT", "WINDIR", "COMSPEC", "SYSTEMDRIVE", "TEMP", "TMP",
  "USERPROFILE", "HOMEDRIVE", "HOMEPATH", "USERNAME", "APPDATA", "LOCALAPPDATA",
  "PROGRAMDATA", "PROGRAMFILES", "PROGRAMFILES(X86)", "PROGRAMW6432",
  "COMMONPROGRAMFILES", "COMMONPROGRAMFILES(X86)", "NUMBER_OF_PROCESSORS",
  "PROCESSOR_ARCHITECTURE", "OS"];
export const POSIX_BASE_ENV = ["PATH", "HOME", "USER", "LOGNAME", "LANG", "LC_ALL",
  "LC_CTYPE", "TMPDIR", "TZ", "TERM"];
const PYTHON_NAMES = ["python", "pythonw", "python3"];
const IS_WINDOWS = process.platform === "win32";

const profile = (name, o = {}) => Object.freeze({ name, before: [], after: [], env: [],
  proven: false, tested: "", ...o });
// The evidence for each profile lives in PROBES.md.
export const PROFILES = Object.freeze({
  claude: profile("claude", { after: ["--setting-sources", "user", "--strict-mcp-config",
    "--tools", ""], env: ["CLAUDE_CONFIG_DIR"], proven: true, tested: "2.1.251" }),
  // The prompt goes on stdin with "-": a batch shim refuses most punctuation.
  codex: profile("codex", { before: ["exec", "--ignore-user-config", "--ignore-rules",
    "--ephemeral", "--skip-git-repo-check", "--sandbox", "read-only", "--disable", "hooks",
    "--disable", "plugins", "--disable", "memories", "--disable", "apps",
    "-c", "project_doc_max_bytes=0", "-c", "skills.include_instructions=false"],
    env: ["CODEX_HOME"], proven: true, tested: "0.144.6" }),
  gemini: profile("gemini"),
  opencode: profile("opencode"),
});

export class SpawnRefused extends Error {
  /** The child was not started. `code` is a stable machine-readable reason. */
  constructor(code, message) {
    super(message);
    this.name = "SpawnRefused";
    this.code = code;
  }
}

function runnable(p) {
  try {
    if (!fs.statSync(p).isFile()) return false;
    fs.accessSync(p, fs.constants.X_OK);
    return true;
  } catch {
    return false; // missing or not executable: not a candidate
  }
}

function isAbsolute(p, windows) {
  // On Windows "\tools" hangs off the current drive, so it needs a drive or share too.
  if (windows) return path.win32.isAbsolute(p) && /^([a-zA-Z]:|\\\\)/.test(p);
  return path.posix.isAbsolute(p);
}

function getVar(env, key) {
  if (key in env) return env[key];
  const low = key.toLowerCase();
  const hit = Object.keys(env).find((k) => k.toLowerCase() === low);
  return hit === undefined ? undefined : env[hit];
}

function fromAbsolute(p, exists, windows, suffixes, code) {
  if (!isAbsolute(p, windows)) {
    throw new SpawnRefused(code, "the configured executable is not an absolute path");
  }
  let candidates = [p];
  if (windows && !STARTABLE.includes(path.win32.extname(p).toLowerCase())) {
    candidates = suffixes.map((s) => p + s);
  }
  const found = candidates.find((c) => exists(c));
  if (!found) throw new SpawnRefused(code, "the configured executable is not a runnable file");
  return found;
}

/** [device, file index], the index 0n where the filesystem keeps none; null if unreadable. */
function identity(p) {
  try {
    const st = fs.statSync(p, { bigint: true });
    return [st.dev, st.ino];
  } catch {
    return null; // missing or unreadable: compared by name only
  }
}

/** One folder by identity. With `unsure`, a folder without a file index matches any
 * folder on its device, since such a filesystem can hide a second name for it. */
function same(a, b, unsure) {
  if (a === null || b === null || a[0] !== b[0]) return false;
  return (a[1] === b[1] && b[1] !== 0n) || (unsure && (a[1] === 0n || b[1] === 0n));
}

/** `p` resolved through links; a missing tail is kept as written. */
function realFolder(p, lib) {
  const tail = [];
  for (let at = p; ; at = lib.dirname(at)) {
    try {
      return lib.join(fs.realpathSync.native(at), ...tail);
    } catch {
      if (lib.dirname(at) === at) return lib.isAbsolute(p) ? lib.resolve(p) : p;
      tail.unshift(lib.basename(at));
    }
  }
}

/** [name, identity] for the resolved folder `here`, then each folder above it. */
function chain(here, windows) {
  const lib = windows ? path.win32 : path.posix;
  const out = [];
  for (; ; here = lib.dirname(here)) {
    out.push([windows ? here.toLowerCase() : here, identity(here)]);
    if (lib.dirname(here) === here) return out;
  }
}

const meets = (c, [name, key], unsure = false) => c.some(([n, k]) => n === name || same(k, key, unsure));

/** The exact folders the caller already runs code from; nothing below them. */
function trustedFolders(windows) {
  const lib = windows ? path.win32 : path.posix;
  const own = [path.dirname(process.execPath)];
  const root = windows ? getVar(process.env, "SystemRoot") : "";
  if (root) own.push(root, lib.join(root, "System32"), lib.join(root, "SysWOW64"));
  return own.filter(Boolean).map((f) => chain(realFolder(f, lib), windows)[0]);
}

/** A function giving a PATH entry's real folder, or null when the entry reaches a
 * working folder (see above). null on a simulated platform: no real folders to read. */
function reachTest(cwd, windows) {
  if (windows !== IS_WINDOWS) return null; // a simulated platform has no real folders to read
  const lib = windows ? path.win32 : path.posix;
  const folders = cwd == null ? [] : [cwd];
  try {
    folders.push(process.cwd());
  } catch {
    // a deleted working folder: no path reaches it
  }
  let home = [];
  try {
    const h = os.homedir();
    if (h && lib.isAbsolute(h)) home = chain(realFolder(h, lib), windows);
  } catch {
    // no home folder is known
  }
  const trusted = trustedFolders(windows);
  const guarded = folders.map((f) => chain(realFolder(f, lib), windows))
    .filter((c) => !trusted.some((t) => meets(c.slice(0, 1), t)))
    .map((c) => [c[0], c.length === 1 || meets(home, c[0])]);
  return (entry) => {
    const real = realFolder(entry, lib);
    const c = chain(real, windows);
    if (trusted.some((t) => meets(c.slice(0, 1), t))) return real;
    return guarded.some(([f, wide]) => meets(wide ? c.slice(0, 1) : c, f, true)) ? null : real;
  };
}

/** [as written, as read] per entry. POSIX reads an entry literally, so a quote or a
 * leading space makes it relative there. Windows reads it as cmd.exe does: a ";"
 * between double quotes does not split, and every quote goes. */
function split(value, windows) {
  if (!windows) return value.split(":").map((r) => [r, r]);
  const out = [];
  let start = 0;
  let quoted = false;
  for (let i = 0; i < value.length; i += 1) {
    if (value[i] === '"') {
      quoted = !quoted;
    } else if (value[i] === ";" && !quoted) {
      out.push(value.slice(start, i));
      start = i + 1;
    }
  }
  out.push(value.slice(start));
  return out.map((r) => [r, r.replaceAll('"', "").trim()]);
}

/** [to hand on, to search] for each absolute PATH entry that reaches no working folder.
 * With `admit`, the folder searched is the entry's real folder. A folder holding the
 * separator leaves: Windows programs disagree on a quoted one, and POSIX cannot write
 * one. The entry goes on as written only where every reader takes it the same way. */
function pathEntries(value, windows, admit = null) {
  const sep = windows ? ";" : ":";
  const norm = (p) => (windows ? p.replaceAll("/", "\\").toLowerCase() : p);
  const out = [];
  for (const [raw, bare] of split(value || "", windows)) {
    if (!bare || !isAbsolute(bare, windows)) continue;
    const real = admit ? admit(bare) : bare;
    if (real === null || real.includes(sep)) continue;
    const kept = (raw === bare || raw === `"${bare}"`) && norm(real) === norm(bare);
    out.push([kept ? raw : real, real]);
  }
  return out;
}

/** The absolute path of `name` (a bare name, or an absolute path), or SpawnRefused.
 * `cwd` is the folder named for the child; PATH entries reaching it are skipped too. */
export function resolve(name, { overrideVar, environ = process.env, exists = runnable,
  windows = IS_WINDOWS, cwd = null } = {}) {
  const listed = windows ? (getVar(environ, "PATHEXT") || ".COM;.EXE;.BAT;.CMD").split(";") : [];
  const suffixes = listed.filter((s) => STARTABLE.includes(s.toLowerCase()));
  const configured = overrideVar ? (getVar(environ, overrideVar) || "").trim() : "";
  if (configured) return fromAbsolute(configured, exists, windows, suffixes, "BAD_OVERRIDE");
  if (name.includes("/") || name.includes("\\")) {
    return fromAbsolute(name, exists, windows, suffixes, "BAD_PATH");
  }
  if (windows && name.includes(":")) { // "C:tool" names a file in the current folder of drive C:
    throw new SpawnRefused("BAD_PATH", "a bare name holding a colon was refused; "
      + "give a bare name or a full path");
  }
  const lib = windows ? path.win32 : path.posix;
  const admit = reachTest(cwd, windows);
  const dirs = pathEntries(getVar(environ, "PATH"), windows, admit).map(([, folder]) => folder);
  const groups = windows ? [[name + ".exe"], suffixes.map((s) => name + s)] : [[name]];
  for (const group of groups) {
    for (const d of dirs) {
      for (const n of group) {
        const candidate = lib.join(d, n);
        if (exists(candidate)) return candidate;
      }
    }
  }
  const hint = overrideVar ? ` or set ${overrideVar} to its full path` : "";
  throw new SpawnRefused("NOT_FOUND", `${name} was not found on PATH; install it${hint}`);
}

export function isBatch(p, windows = IS_WINDOWS) {
  return windows && BATCH_SUFFIXES.includes(path.win32.extname(p).toLowerCase());
}

/** True when cmd.exe would read part of this argument as a command. */
export function cmdUnsafe(arg) {
  if ([...arg].some((c) => CMD_UNSAFE.has(c))) return true;
  const quoted = arg === "" || arg.includes(" ") || arg.includes("\t");
  return !quoted && [...arg].some((c) => CMD_UNSAFE_UNQUOTED.has(c));
}

export function isPython(p) {
  const base = path.win32.basename(p).toLowerCase().replace(/\.[^.]*$/, (e) =>
    /^\.\d+$/.test(e) ? e : "");
  return PYTHON_NAMES.includes(base) || /^python3\.\d+$/.test(base);
}

/** The platform base plus `allow`, then `setEnv` on top. Nothing else passes.
 * PATH keeps what `resolve` walks; `cwd` is the folder named for the child. */
export function childEnv({ allow = [], setEnv = {}, environ = process.env,
  windows = IS_WINDOWS, python = false, cwd = null } = {}) {
  const norm = (k) => (windows ? k.toLowerCase() : k);
  const wanted = new Set([...(windows ? WINDOWS_BASE_ENV : POSIX_BASE_ENV), ...allow].map(norm));
  let out = Object.fromEntries(Object.entries(environ).filter(([k]) => wanted.has(norm(k))));
  const admit = reachTest(cwd, windows);
  for (const key of Object.keys(out).filter((k) => k.toUpperCase() === "PATH")) {
    const kept = pathEntries(out[key], windows, admit).map(([r]) => r);
    out[key] = windows ? kept.join(";") : (kept.join(":") || POSIX_FALLBACK_PATH);
  }
  const forced = { ...setEnv };
  if (python) forced.PYTHONSAFEPATH = "1";
  if (windows) forced[NO_CWD_SEARCH] = "1";
  for (const [key, value] of Object.entries(forced)) {
    if (windows) out = Object.fromEntries(Object.entries(out).filter(([k]) => norm(k) !== norm(key)));
    out[key] = value;
  }
  return out;
}

/** The full argv after the profile and batch checks, or SpawnRefused. */
export function buildArgv(exe, args, { profile = null, grants = [], windows = IS_WINDOWS } = {}) {
  const prof = typeof profile === "string" ? PROFILES[profile] : profile;
  if (typeof profile === "string" && !prof) {
    throw new SpawnRefused("UNKNOWN_PROFILE", "no isolation profile has that name");
  }
  if (prof && !prof.proven && !grants.includes(prof.name)) {
    throw new SpawnRefused("GRANT_REQUIRED",
      `the ${prof.name} CLI has no proven isolation profile; a launch grant must name it`);
  }
  const argv = [exe, ...(isPython(exe) ? ["-P"] : []), ...(prof ? prof.before : []),
    ...args, ...(prof ? prof.after : [])];
  if (isBatch(exe, windows) && argv.some(cmdUnsafe)) {
    throw new SpawnRefused("UNSAFE_ARGUMENT", "a batch-file target was refused: an "
      + "argument holds characters cmd.exe would reinterpret");
  }
  return { argv, prof };
}

/** A private folder for files the child reads, and an empty working folder. */
export class Session {
  constructor(tmpdir = os.tmpdir(), prefix = "spawn-") {
    this.root = fs.mkdtempSync(path.join(tmpdir, prefix));
    this.cwd = path.join(this.root, "cwd");
    try {
      fs.mkdirSync(this.cwd);
    } catch (err) {
      this.close();
      throw err;
    }
  }

  write(name, text) {
    if (path.basename(name) !== name || ["", ".", "..", "cwd"].includes(name) || name.includes("\\")) {
      throw new Error("a session file name must be a plain name");
    }
    const p = path.join(this.root, name);
    fs.writeFileSync(p, text, { encoding: "utf8", flag: "wx" });
    return p;
  }

  close() {
    try {
      fs.rmSync(this.root, { recursive: true, force: true });
    } catch (err) {
      process.stderr.write(`[safe_spawn] could not remove a private folder (${err.code})\n`);
    }
  }
}

function stopTree(child) {
  if (IS_WINDOWS) {
    const root = getVar(process.env, "SystemRoot") || "C:\\Windows";
    const r = spawnSync(path.join(root, "System32", "taskkill.exe"),
      ["/F", "/T", "/PID", String(child.pid)], { windowsHide: true, timeout: DRAIN_MS });
    if (r.error) process.stderr.write("[safe_spawn] could not stop the process tree; "
      + "stopping the direct child only\n");
  } else {
    try {
      process.kill(-child.pid, "SIGKILL");
    } catch {
      // the group has already exited
    }
  }
  try { child.kill("SIGKILL"); } catch { /* already gone */ }
}

/** Start argv; resolve {status, stdout, stderr}; a timeout stops the whole tree. */
export function boundedRun(argv, { input, timeout, cwd, env, label = "child" } = {}) {
  let file = argv[0];
  let rest = argv.slice(1);
  const opts = { cwd, env, windowsHide: true, detached: !IS_WINDOWS };
  if (isBatch(file)) {
    const root = getVar(process.env, "SystemRoot") || "C:\\Windows";
    rest = ["/d", "/v:off", "/s", "/c", `"${argv.map((a) => `"${a}"`).join(" ")}"`];
    file = path.join(root, "System32", "cmd.exe");
    opts.windowsVerbatimArguments = true;
  }
  return new Promise((done, fail) => {
    const child = spawn(file, rest, opts);
    let stdout = "";
    let stderr = "";
    let timer = null;
    child.stdout.setEncoding("utf8").on("data", (d) => { stdout += d; });
    child.stderr.setEncoding("utf8").on("data", (d) => { stderr += d; });
    child.on("error", (err) => { clearTimeout(timer); fail(err); });
    child.on("close", (status) => {
      if (timer === "fired") return;
      clearTimeout(timer);
      done({ status, stdout, stderr });
    });
    if (timeout) {
      timer = setTimeout(() => {
        timer = "fired";
        stopTree(child);
        const err = new Error(`${label} timed out after ${timeout / 1000} s`);
        err.code = "ETIMEDOUT";
        fail(err);
      }, timeout);
    }
    child.stdin.on("error", () => { /* the child closed stdin early; its output still counts */ });
    child.stdin.end(input ?? "");
  });
}

/** Resolve, check and start `name`. `args` may be a function of {name: path} for `files`. */
export async function run(name, args = [], { profile = null, overrideVar, input, timeout = 600000,
  allowEnv = [], setEnv = {}, grants = [], cwd = null, files = {}, environ = process.env,
  exists = runnable, windows = IS_WINDOWS, tmpdir, runner = boundedRun } = {}) {
  const exe = resolve(name, { overrideVar, environ, exists, windows, cwd });
  const label = path.win32.basename(name); // never the resolved path
  let session;
  try {
    session = new Session(tmpdir);
  } catch (err) {
    throw new SpawnRefused("UNAVAILABLE", `the private folder could not be made (${err.code})`);
  }
  try {
    const paths = Object.fromEntries(Object.entries(files).map(([n, t]) => [n, session.write(n, t)]));
    const { argv, prof } = buildArgv(exe, typeof args === "function" ? args(paths) : [...args],
      { profile, grants, windows });
    const env = childEnv({ allow: [...allowEnv, ...(prof ? prof.env : [])], setEnv, environ,
      windows, python: isPython(exe), cwd });
    return await runner(argv, { input, timeout, cwd: cwd ?? session.cwd, env, label });
  } catch (err) {
    if (err instanceof SpawnRefused || err.code === "ETIMEDOUT") throw err;
    throw new SpawnRefused("UNAVAILABLE", `${label} could not be started (${err.code || err.name})`);
  } finally {
    session.close();
  }
}
