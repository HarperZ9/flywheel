// Where learn keeps its state, and the checks that keep every state file inside that folder.
//
// The state folder is LEARN_HOME when set, else a per-user data folder: %LOCALAPPDATA%\learn on
// Windows, ~/Library/Application Support/learn on macOS, $XDG_DATA_HOME/learn or
// ~/.local/share/learn elsewhere. Ids that name a file (sessionId, runId) must match ID_PATTERN,
// must not start with a dot or a hyphen (so an id never reads as a flag) and must not be a
// Windows device name. A path outside the folder on its text is refused before anything resolves
// it. A path inside is resolved through real paths (so symlinks and junctions are followed) and
// refused when it lands outside, or when a link on the way does not resolve.
import { homedir } from "node:os";
import path from "node:path";
import { lstatSync, readFileSync, realpathSync } from "node:fs";
import { invalid, notFound, LearnError } from "./errors.mjs";

export const ID_PATTERN = /^[A-Za-z0-9._-]{1,64}$/;
const DEVICE_NAME = /^(con|prn|aux|nul|com[0-9]|lpt[0-9])$/i;

export function stateRoot({ env = process.env, platform = process.platform, home = homedir() } = {}) {
  const lib = platform === "win32" ? path.win32 : path.posix;
  const override = (env.LEARN_HOME || "").trim();
  if (override) return { dir: lib.resolve(override), source: "LEARN_HOME" };
  if (platform === "win32") {
    const local = env.LOCALAPPDATA && lib.isAbsolute(env.LOCALAPPDATA) ? env.LOCALAPPDATA : lib.join(home, "AppData", "Local");
    return { dir: lib.join(local, "learn"), source: "default" };
  }
  if (platform === "darwin") return { dir: lib.join(home, "Library", "Application Support", "learn"), source: "default" };
  const xdg = env.XDG_DATA_HOME && lib.isAbsolute(env.XDG_DATA_HOME) ? env.XDG_DATA_HOME : lib.join(home, ".local", "share");
  return { dir: lib.join(xdg, "learn"), source: "default" };
}

export function checkId(value, name) {
  const ok = typeof value === "string" && ID_PATTERN.test(value) && !value.startsWith(".") && !value.startsWith("-") &&
    !DEVICE_NAME.test(value.split(".")[0]);
  if (!ok) {
    throw invalid(`${name} must be 1 to 64 letters, digits, dots, underscores or hyphens, must not start with a dot or a hyphen, and must not be a device name`);
  }
  return value;
}

// Whether a directory entry exists at `p` itself, without following a link there.
function entryExists(p) {
  try {
    lstatSync(p);
    return true;
  } catch (err) {
    if (err.code === "ENOENT" || err.code === "ENOTDIR") return false;
    throw err;
  }
}

// The real path of `p`: the nearest existing ancestor is resolved through links, and the
// segments that do not exist yet are appended unchanged. An entry that exists but does not
// resolve is a link whose target is missing; a write would follow it wherever it points, so the
// result is null and the caller treats the path as outside.
function realish(p) {
  let cur = path.resolve(p);
  const rest = [];
  for (;;) {
    try {
      return path.join(realpathSync.native(cur), ...rest.reverse());
    } catch (err) {
      if (err.code !== "ENOENT" && err.code !== "ENOTDIR") throw err;
      if (entryExists(cur)) return null;
      const parent = path.dirname(cur);
      if (parent === cur) return path.resolve(p);
      rest.push(path.basename(cur));
      cur = parent;
    }
  }
}

// Containment on the text of two paths, without touching the filesystem.
function under(root, p) {
  const rel = path.relative(path.resolve(root), path.resolve(p));
  return rel === "" || (!path.isAbsolute(rel) && rel.split(path.sep)[0] !== "..");
}

// A path outside the state folder on its text (another drive, `..`, a UNC share such as
// \\host\share) is refused before anything resolves it: on Windows, resolving a UNC path opens an
// SMB or WebDAV connection to that host. Only a path already inside is resolved through links.
export function isInside(root, p) {
  if (!under(root, p)) return false;
  const base = realish(root);
  const real = realish(p);
  return base !== null && real !== null && under(base, real);
}

// `<root>/<area>/<id><suffix>`, after the id and the resolved location are checked.
export function stateFile(root, area, id, suffix, name) {
  checkId(id, name);
  const file = path.join(root, area, id + suffix);
  if (!isInside(root, file)) throw invalid(`${name} resolves outside the learn state folder`);
  return file;
}

// A caller-supplied path, resolved against the state folder and refused outside it.
export function confinedPath(root, p, name) {
  if (typeof p !== "string" || !p || p.includes("\0")) throw invalid(`${name} must be a path inside the learn state folder`);
  const abs = path.resolve(root, p);
  if (!isInside(root, abs)) throw invalid(`${name} must be a path inside the learn state folder`);
  return abs;
}

// Read a JSON file for a tool. Failures carry fixed text: no file bytes, no built path.
export function readJson(file, name) {
  let text;
  try {
    text = readFileSync(file, "utf8");
  } catch (err) {
    if (err.code === "ENOENT" || err.code === "ENOTDIR") throw notFound(`no file found for ${name} inside the learn state folder`);
    if (err.code === "EISDIR") throw invalid(`${name} names a folder, not a file`);
    throw new LearnError("INTERNAL", `the file for ${name} could not be read`);
  }
  try {
    return JSON.parse(text);
  } catch {
    throw invalid(`the file for ${name} is not valid JSON`);
  }
}
