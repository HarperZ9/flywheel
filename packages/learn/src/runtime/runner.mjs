import { decide } from "../accountability/gate.mjs";
import { observe, sha256hex } from "../accountability/witness.mjs";
import { Ledger } from "../accountability/ledger.mjs";
import { getAdapter } from "../adapters/types.mjs";
import { STEP_KINDS } from "../workflow/schema.mjs";

async function actuate(step, driver) {
  switch (step.kind) {
    case "navigate": return driver.navigate(step.target);
    case "click": return driver.click(step.target);
    case "fill": return driver.fill(step.target, step.value ?? "");
    case "waitFor": return driver.waitFor(step.target);
    case "capture": return driver.capture(step.capture ?? "dom");
    case "submit": return driver.click(step.target ?? step.submit ?? "[type=submit]");
    default: return { payload: "noop:" + step.kind };
  }
}

// Options that grant actuation (see gate.mjs): submissionMode "witnessed-auto" lets the engine
// perform `submit` steps, allowCost lets it perform `cost` or `irreversible` steps, and
// allowIrreversible is the library shorthand for both. authorizedBy and costAuthorizedBy name
// the grant in the ledger entry of each step it allowed, so a receipt shows who authorized what.
export async function run(workflow, { driver, allowIrreversible = false, allowCost = false, submissionMode = "manual",
  authorizedBy = null, costAuthorizedBy = null, fromSeq = 0, ledger = new Ledger(), humanAttest = null } = {}) {
  // Default-deny against the engine's GLOBAL allowlist of known step kinds — NOT the workflow's
  // own kinds (which would be tautological). A step kind outside STEP_KINDS is refused.
  const sealedKinds = STEP_KINDS;
  // "witnessed-auto" authorizes the engine to perform `submit` steps (witnessed); "manual" halts them.
  // This NEVER affects `assess` (graded work), which always halts for the operator regardless.
  const autoSubmit = submissionMode === "witnessed-auto";
  // If resuming straight after a human-gate, the caller attaches the human attestation for that seq.
  if (humanAttest) ledger.append({ kind: "human-assessment", seq: humanAttest.seq, note: humanAttest.note, at: humanAttest.at });
  let completion = null;
  for (let i = fromSeq; i < workflow.steps.length; i++) {
    const step = workflow.steps[i];
    const g = decide(step, { sealedKinds, allowIrreversible, autoSubmit, allowCost });
    if (g.decision === "deny") {
      ledger.append({ kind: "decision", seq: i, decision: "deny", reason: g.reason, stepKind: step.kind });
      return { status: "denied", haltedAt: i, ledger, completion };
    }
    if (g.decision === "needs-human") {
      ledger.append({ kind: "human-gate", seq: i, stepKind: step.kind, label: step.label ?? null, reason: g.reason });
      return { status: step.kind === "assess" ? "halted-assess" : "halted-needs-human", haltedAt: i, ledger, completion };
    }
    try {
      const before = await driver.snapshot();
      const res = await actuate(step, driver);
      const after = await driver.snapshot();
      const obs = observe({ organ: "actuation", subject: step.kind + ":" + (step.target ?? ""), summary: res.payload,
        payload: JSON.stringify({ before, res, after }), data: { url: after.url } });
      const entry = { kind: "step", seq: i, stepKind: step.kind, digest: obs.digest, summary: res.payload };
      if (res.evidenceRef) {
        entry.evidenceRef = res.evidenceRef;
      }
      if (step.kind === "submit") {
        // Witnessed automated submission: record the mode + a digest of the exact pre-submit page
        // state, so the receipt proves what was submitted and that the operator authorized it.
        entry.submission = "witnessed-auto";
        entry.submittedStateDigest = "sha256:" + sha256hex(JSON.stringify(before));
        entry.authorizedBy = allowIrreversible ? "allowIrreversible" : (authorizedBy ?? "submissionMode witnessed-auto");
      }
      if (step.cost || step.irreversible) entry.costAuthorizedBy = allowIrreversible ? "allowIrreversible" : (costAuthorizedBy ?? "allowCost");
      ledger.append(entry);
      if (step.kind === "complete") {
        completion = await getAdapter(workflow.adapter).captureCompletion(driver);
        ledger.append({ kind: "completion", seq: i, certId: completion.certId, payload: completion.payload });
      }
    } catch (err) {
      ledger.append({ kind: "error", seq: i, stepKind: step.kind, message: String((err && err.message) || err) });
      return { status: "halted-error", haltedAt: i, ledger, completion };
    }
  }
  return { status: "completed", haltedAt: null, ledger, completion };
}

export async function resume(workflow, { driver, ledger, haltedAt, allowIrreversible = false, allowCost = false,
  submissionMode = "manual", authorizedBy = null, costAuthorizedBy = null, humanAttest = null } = {}) {
  return run(workflow, { driver, ledger, allowIrreversible, allowCost, submissionMode, authorizedBy, costAuthorizedBy,
    fromSeq: haltedAt + 1, humanAttest });
}
