import { sha256hex } from "../accountability/witness.mjs";

export const STEP_KINDS = new Set([
  "navigate", "click", "fill", "waitFor", "capture", "submit", "assess", "complete",
]);
// kinds that require a `target`
const NEEDS_TARGET = new Set(["navigate", "click", "fill", "waitFor"]);

export function loadWorkflow(obj) {
  if (!obj || typeof obj !== "object") throw new Error("workflow must be an object");
  if (!Array.isArray(obj.steps) || obj.steps.length === 0) throw new Error("workflow needs a non-empty steps array");
  const steps = obj.steps.map((s, i) => {
    if (!s || !STEP_KINDS.has(s.kind)) throw new Error(`unknown step kind: ${s && s.kind}`);
    if (NEEDS_TARGET.has(s.kind) && !s.target) throw new Error(`step ${i} (${s.kind}) requires a target`);
    return { ...s, id: i };
  });
  const seal = "sha256:" + sha256hex(JSON.stringify(steps));
  return { adapter: obj.adapter || "fake", course: obj.course || "", steps, seal };
}
