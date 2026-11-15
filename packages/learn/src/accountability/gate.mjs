// The gate: one decision per step, before anything is actuated.
//
// Grants, each of which a person gives on the command line for one invocation:
//   autoSubmit          the engine may perform `submit` steps (witnessed-auto submission mode)
//   allowCost           the engine may perform steps flagged `cost` or `irreversible`
//   allowIrreversible   library-only shorthand for both; the CLI never sets it
// A step that is both a submit and a cost needs both grants. `assess` and sensitive `fill`
// steps halt under every grant.
export function decide(step, { sealedKinds, allowIrreversible = false, autoSubmit = false, allowCost = false } = {}) {
  if (!sealedKinds || !sealedKinds.has(step.kind)) return { decision: "deny", reason: "undeclared step kind" };
  if (step.kind === "assess") return { decision: "needs-human", reason: "graded step — the operator performs it; the engine never answers it" };
  if (step.kind === "fill" && step.sensitive) return { decision: "needs-human", reason: "credential/payment/CAPTCHA — operator only" };
  // `complete` is a safe capture (reads the certificate), not a submission; it is not gated here.
  const isSubmit = step.kind === "submit";
  const isCost = !!(step.cost || step.irreversible);
  if (!isSubmit && !isCost) return { decision: "allow", reason: "declared logistics step" };
  if (allowIrreversible) return { decision: "allow", reason: "the caller authorized submission and cost steps for this run" };
  if (isCost && !allowCost) return { decision: "needs-human", reason: "cost or irreversible step halts for the operator (not authorized with --allow-cost)" };
  if (isSubmit && !autoSubmit) return { decision: "needs-human", reason: "submission halts for the operator (manual submission)" };
  return { decision: "allow", reason: isSubmit ? "operator authorized witnessed automated submission" : "operator authorized this cost step with --allow-cost" };
}
