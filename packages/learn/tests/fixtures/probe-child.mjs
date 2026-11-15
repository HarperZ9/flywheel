// Test-only stand-in for a peer CLI. It records what a child started by learn can see (its
// working folder, whether planted or named variables reached it, and the safety switches) in a
// report beside the file learn passes as the last argument, then prints a render-result JSON.
import { readdirSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";

const target = process.argv[process.argv.length - 1];
const report = {
  cwd: process.cwd(),
  cwdEntries: readdirSync(process.cwd()),
  sawPlanted: process.env.LEARN_PROBE_PLANTED ?? null,
  sawPassed: process.env.LEARN_PROBE_PASSED ?? null,
  noDefaultCwd: process.env.NoDefaultCurrentDirectoryInExePath ?? null,
  pythonSafePath: process.env.PYTHONSAFEPATH ?? null,
};
writeFileSync(join(dirname(target), "probe-report.json"), JSON.stringify(report));
process.stdout.write(JSON.stringify({ verdict: "MATCH", selected_profile: "probe" }));
