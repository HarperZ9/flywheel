import { realpathSync } from "node:fs";
import { fileURLToPath } from "node:url";

// True when `metaUrl` is the module node was asked to run. Both sides go through realpath, so a
// bin that npm linked (a symlink on Linux and macOS) or a junctioned folder still counts, while a
// test that imports the module does not.
export function isMain(metaUrl, argv1 = process.argv[1]) {
  if (!argv1) return false;
  let started;
  let self;
  try {
    started = realpathSync.native(argv1);
    self = realpathSync.native(fileURLToPath(metaUrl));
  } catch (err) {
    if (err.code === "ENOENT") return false; // `node -e` or a deleted file: not a program start
    throw err;
  }
  return process.platform === "win32" ? started.toLowerCase() === self.toLowerCase() : started === self;
}
