// Self-explanation module — the "explain it back" retrieval-practice technique. The operator
// writes their OWN explanation of a concept; this module wraps it into a crucible thesis (reusing
// assist + toCrucibleThesis, exactly as the assist pillar does for any draft) and grades the
// resulting MATCH/DRIFT/UNVERIFIABLE verdicts into human-readable buckets.
//
// INTEGRITY: this checks the operator's OWN explanation against THEIR OWN cited sources. It
// supplies nothing — no "correct answer", no rewritten/fixed claim, no fabricated evidence. The
// falsification field is always left blank for the operator/crucible to fill in; gradeExplanation
// only reads back verdicts crucible already produced and buckets them for study. Never shells out
// to crucible itself here (that is crucibleAssess's job); this module only builds the thesis and
// grades verdicts the caller obtained.
import { assist } from "../assist/assist.mjs";
import { toCrucibleThesis } from "../interop/crucible.mjs";

// explanationThesis(explanationText) -> a crucible thesis built from the operator's OWN
// explanation (via assist() -> toCrucibleThesis()), exactly as any other draft is wrapped.
export function explanationThesis(explanationText, opts = {}) {
  const a = assist(explanationText, opts);
  return toCrucibleThesis(a, { title: "Self-explanation — claims to verify", ...opts });
}

// gradeExplanation(crucibleVerdicts) -> {grounded, shaky, unverifiable, summary}
// Buckets each verdict item ({text, verdict, ...}) by its crucible verdict:
//   MATCH        -> grounded    (the operator's explanation held up against their own sources)
//   DRIFT        -> shaky       (partially/inconsistently supported — worth re-studying)
//   anything else (UNVERIFIABLE, unrecognized, missing) -> unverifiable, fail-closed: an
//   unrecognized verdict string is never silently dropped or treated as a pass.
export function gradeExplanation(crucibleVerdicts) {
  const grounded = [];
  const shaky = [];
  const unverifiable = [];

  for (const v of crucibleVerdicts || []) {
    if (v && v.verdict === "MATCH") grounded.push(v);
    else if (v && v.verdict === "DRIFT") shaky.push(v);
    else unverifiable.push(v);
  }

  const summary = `${grounded.length} grounded, ${shaky.length} shaky, ${unverifiable.length} unverifiable`;
  return { grounded, shaky, unverifiable, summary };
}
