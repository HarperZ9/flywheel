// gather interop: turn assist-extracted sources into a gather manifest, and optionally run the
// gather CLI to mint source receipts. Zero-dep (node builtins).
import { parseCommand, runPeer, refusalReason } from "./spawn.mjs";

export function toGatherManifest(assistResult) {
  return { sources: [...new Set(assistResult.sources || [])] };
}

// Optional. Configure LEARN_GATHER_CMD as a JSON argv array, for example
// ["python", "-m", "gather"], or the whitespace form `python -m gather`. The command must accept
// `run <url>`. Each source starts one child through spawn.mjs, one after another.
export async function gatherRun(sources, { cmd = process.env.LEARN_GATHER_CMD } = {}) {
  let argv;
  try {
    argv = parseCommand(cmd);
  } catch (err) {
    return { ran: false, reason: refusalReason("LEARN_GATHER_CMD", err) };
  }
  if (!argv) return { ran: false, reason: "no gather command configured (set LEARN_GATHER_CMD)" };
  const receipts = [];
  for (const s of sources) {
    try {
      const res = await runPeer(argv, ["run", s]);
      receipts.push({ source: s, ran: true, code: res.status ?? null, out: (res.stdout || "").slice(0, 400) });
    } catch (err) {
      receipts.push({ source: s, ran: false, code: null, out: "", reason: refusalReason("gather", err) });
    }
  }
  return { ran: true, receipts };
}
