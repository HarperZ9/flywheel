// Start a peer CLI named by LEARN_CRUCIBLE_CMD, LEARN_GATHER_CMD or LEARN_TELOS_CMD through the
// vendored safe spawn helper (src/_vendor/safe_spawn.mjs, hash-pinned in VENDORED.sha256):
// the executable resolves to an absolute path, the child runs in a new private empty folder with
// an environment allowlist (extended only by the names in LEARN_CHILD_ENV), Windows children get
// NoDefaultCurrentDirectoryInExePath=1, and a Python child gets -P and PYTHONSAFEPATH=1. A bare
// name is looked up on PATH without any entry that reaches the folder learn runs in, and the
// child's PATH leaves those entries out as well. In a filesystem root, at home or above it, only
// an entry naming that folder itself leaves; node's folder and the Windows, System32 and SysWOW64
// folders always stay, and a working folder that is one of them guards nothing.
// Because the child's folder is private, every path handed to it must be absolute.
import { run as safeRun, SpawnRefused } from "../_vendor/safe_spawn.mjs";

const RELATIVE = /^\.{1,2}([\\/]|$)/;

export class CommandRefused extends Error {
  constructor(reason) {
    super(reason);
    this.name = "CommandRefused";
  }
}

// The command as argv: a JSON array (keeps a path with spaces whole, the recommended form) or a
// whitespace-separated string (the 1.x form). null when the variable is empty.
export function parseCommand(value) {
  const text = String(value ?? "").trim();
  if (!text) return null;
  let argv;
  if (text.startsWith("[")) {
    try {
      argv = JSON.parse(text);
    } catch {
      throw new CommandRefused("is not a valid JSON argv array");
    }
    if (!Array.isArray(argv) || !argv.length || !argv.every((a) => typeof a === "string" && a.length)) {
      throw new CommandRefused("must be a JSON array of non-empty strings");
    }
  } else {
    argv = text.split(/\s+/);
  }
  if (argv.some((a) => RELATIVE.test(a))) {
    throw new CommandRefused("holds a relative path; the child runs in a private folder, so give an absolute path");
  }
  return argv;
}

export function childAllowEnv(env = process.env) {
  return (env.LEARN_CHILD_ENV || "").split(",").map((s) => s.trim()).filter(Boolean);
}

// Resolves {status, stdout, stderr}. Throws SpawnRefused or a timeout error from the helper.
export function runPeer(argv, args, { timeout = 120000 } = {}) {
  return safeRun(argv[0], [...argv.slice(1), ...args], {
    timeout, allowEnv: childAllowEnv(), setEnv: { PYTHONSAFEPATH: "1" },
  });
}

// One line on why a child did not run. It never holds a resolved path or a variable's value.
export function refusalReason(label, err) {
  if (err instanceof CommandRefused) return `${label} ${err.message}`;
  if (err instanceof SpawnRefused) return `${label} was not started (${err.code}): ${err.message}`;
  if (err && err.code === "ETIMEDOUT") return `${label} timed out`;
  return `${label} could not be started`;
}
