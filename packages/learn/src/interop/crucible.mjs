// crucible interop — turn assist-extracted claims into a crucible thesis (the exact shape
// crucible_assess consumes: {title, disposition, claims:[{text, falsification}]}), and optionally
// run the crucible CLI to get MATCH/DRIFT/UNVERIFIABLE verdicts. Zero-dep (node builtins).
import { resolve } from "node:path";
import { parseCommand, runPeer, refusalReason } from "./spawn.mjs";

export function toCrucibleThesis(assistResult, { title = "Assisted work — claims to verify", disposition = "publishable" } = {}) {
  return {
    title,
    disposition,
    // Operator (or crucible measurements) supplies falsification/evidence; text is the operator's claim.
    claims: (assistResult.claims || []).map((c) => ({ text: c.text, falsification: "" })),
  };
}

// Optional. Configure LEARN_CRUCIBLE_CMD as a JSON argv array, for example
// ["python", "-m", "crucible"], or the whitespace form `python -m crucible`. The command must
// accept `assess <thesis>`. It starts through spawn.mjs; see there for the isolation it gets.
export async function crucibleAssess(thesisPath, { cmd = process.env.LEARN_CRUCIBLE_CMD, measurementsPath = null } = {}) {
  let argv;
  try {
    argv = parseCommand(cmd);
  } catch (err) {
    return { ran: false, reason: refusalReason("LEARN_CRUCIBLE_CMD", err) };
  }
  if (!argv) return { ran: false, reason: "no crucible command configured (set LEARN_CRUCIBLE_CMD)" };
  const args = ["assess", resolve(thesisPath)];
  if (measurementsPath) args.push(resolve(measurementsPath));
  let res;
  try {
    res = await runPeer(argv, args);
  } catch (err) {
    return { ran: false, reason: refusalReason("crucible", err) };
  }
  let verdicts = null;
  try { verdicts = JSON.parse(res.stdout); } catch { /* not JSON: the raw stdout is returned instead */ }
  return { ran: true, code: res.status, verdicts, stdout: res.stdout };
}
