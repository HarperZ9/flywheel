// Operator-spine self-check: exercises the load-bearing integrity invariants AT RUNTIME and
// reports MATCH / DEGRADED (like crucible_doctor). If any construction were weakened, a check fails.
import { version } from "./index.mjs";
import { decide } from "./accountability/gate.mjs";
import { Ledger } from "./accountability/ledger.mjs";
import { run } from "./runtime/runner.mjs";
import { loadWorkflow, STEP_KINDS } from "./workflow/schema.mjs";
import { FakeDriver } from "./actuation/driver.mjs";
import "./adapters/fake.mjs";
import { telosRender, toAidLedgerEntry } from "./interop/telos.mjs";
import { buildReceipt } from "./receipt/receipt.mjs";
import { newSession, recordAttempt, mastery, recordVisualization } from "./tutor/tutor.mjs";
import { recordPrediction } from "./tutor/predict.mjs";
import { reverifySelfCheck } from "./tutor/reverify.mjs";
import { proofLessonSelfCheck } from "./tutor/prooflessonverify.mjs";
import { newSessionWithFSRS, recordAttemptWithGrade } from "./tutor/tutor.mjs";
import { deriveScheduleReceipt } from "./tutor/fsrsderive.mjs";
import { choiceSelfCheck } from "./tutor/choice.mjs";

export async function doctor() {
  const checks = [];
  const add = (name, ok, detail = "") => checks.push({ name, status: ok ? "MATCH" : "FAIL", detail });

  // 1. assess never resolves to allow
  add("gate.assess_never_allow",
    decide({ kind: "assess" }, { sealedKinds: STEP_KINDS, allowIrreversible: true }).decision === "needs-human");

  // 2. e2e: an assess step halts before any actuation
  const wf = loadWorkflow({ adapter: "fake", course: "doctor", steps: [{ kind: "assess", label: "x" }, { kind: "complete" }] });
  const d1 = new FakeDriver();
  const r1 = await run(wf, { driver: d1 });
  add("runtime.assess_halts_no_actuation", r1.status === "halted-assess" && d1.actions.length === 0);

  // 3. default-deny: an undeclared step kind is denied, nothing actuated
  const d2 = new FakeDriver();
  const r2 = await run({ adapter: "fake", course: "d", seal: "x", steps: [{ kind: "wipe", id: 0 }] }, { driver: d2 });
  add("runtime.default_deny_undeclared", r2.status === "denied" && d2.actions.length === 0);

  // 4. ledger tamper is detected
  const l = new Ledger(); l.append({ a: 1 }); l.append({ a: 2 }); l.entries()[0].entry.a = 9;
  add("ledger.tamper_detected", l.verify().ok === false);

  // 5. telos render is fail-closed with no engine configured (never throws, tagged aid)
  const fc = await telosRender("x.json", { cmd: "" });
  add("telos.render_fail_closed", fc.ran === false && fc.verdict === "UNVERIFIABLE" && fc.provenance === "aid");

  // 6. an aid render is filed under aidVisualizations and NEVER as graded work
  const al = new Ledger();
  al.append(toAidLedgerEntry({ verdict: "MATCH", result_hash: "sha256:b" }, { concept: "probe", seq: 0 }));
  const rj = buildReceipt({ workflow: { course: "d", seal: "s" }, ledger: al, completion: null }).json;
  add("receipt.aid_never_graded", rj.aidVisualizations.length === 1 && rj.humanAssessments.length === 0 && rj.witnessedAutoSubmissions.length === 0 && rj.manualSubmissions.length === 0);

  // 7. mastery is render/visualization-independent: a session with a mastered practice log stays
  // MATCH (ready, same accuracy) regardless of attached aid renders — attaching a visualization
  // must never move the needle on mastery. Separately, a PENDING prediction (correct: null) must
  // never be silently read as a correct attempt — mastery is a function of the operator's own
  // SCORED practice attempts only, never of a render or an unscored prediction.
  const ms = newSession({ topic: "doctor-probe", objectives: ["x"] });
  recordAttempt(ms, { objective: "x", prompt: "q1", answer: "a", correct: true });
  recordAttempt(ms, { objective: "x", prompt: "q2", answer: "a", correct: true });
  recordAttempt(ms, { objective: "x", prompt: "q3", answer: "a", correct: true });
  const masteryBefore = mastery(ms, { threshold: 0.8, minAttempts: 3 });
  recordVisualization(ms, { objective: "x", render: { verdict: "MATCH", result_hash: "sha256:doctor" } });
  const masteryAfterViz = mastery(ms, { threshold: 0.8, minAttempts: 3 });
  recordPrediction(ms, { objective: "x", prompt: "predict", prediction: "pending" }); // correct: null
  const masteryAfterPrediction = mastery(ms, { threshold: 0.8, minAttempts: 3 });
  add("tutor.mastery_render_visualization_independent",
    masteryBefore.ready === true &&
    masteryAfterViz.ready === true &&
    masteryAfterViz.perObjective[0].correct === masteryBefore.perObjective[0].correct &&
    masteryAfterViz.perObjective[0].attempts === masteryBefore.perObjective[0].attempts &&
    ms.visualizations.length === 1 &&
    // the pending prediction is counted as an attempt but NEVER as correct (no silent pass)
    masteryAfterPrediction.perObjective[0].attempts === masteryBefore.perObjective[0].attempts + 1 &&
    masteryAfterPrediction.perObjective[0].correct === masteryBefore.perObjective[0].correct);

  // 8. the tutor-receipt re-verifier can FAIL: it must pass a clean receipt and reject each
  // known-bad fixture (tampered chain entry, hand-edited verdict, chainless receipt). A verifier
  // that cannot fail on a known-bad input is not a verifier.
  add("tutor.reverify_rejects_known_bad", reverifySelfCheck());

  // 9. the proof-lesson pipeline can FAIL: a clean packet derives a lesson whose verdict is the
  // packet's verdict and whose scaffold never dumps the packet's reasoning, while each known-bad
  // input is rejected (forged verdict enum, tampered chain entry, verdict flipped MATCH-from-DRIFT,
  // chainless receipt). A verifier that cannot fail on a known-bad input is not a verifier.
  add("tutor.prooflesson_rejects_known_bad", proofLessonSelfCheck());

  // 10. the FSRS schedule is a RE-DERIVABLE function of the witnessed graded log, and the audit can
  // FAIL: a clean session re-derives to MATCH, and tampering the cached itemState (which never feeds
  // the mastery gate) is caught as DRIFT rather than trusted. A schedule audit that cannot detect a
  // tampered cache is not an audit.
  const fs = newSessionWithFSRS({ topic: "doctor-fsrs", objectives: ["x"] });
  recordAttemptWithGrade(fs, { objective: "x", grade: 3, now: "2026-06-30T00:00:00.000Z" });
  recordAttemptWithGrade(fs, { objective: "x", grade: 4, now: "2026-07-02T00:00:00.000Z" });
  const cleanVerdict = deriveScheduleReceipt(fs).verdict;
  fs.itemState.x.stability = 99999; // tamper the cached hint
  const tamperedVerdict = deriveScheduleReceipt(fs).verdict;
  add("tutor.schedule_rederivable_from_log", cleanVerdict === "MATCH" && tamperedVerdict === "DRIFT");

  // 11. a choice item's diagnosis names the misconception behind a wrong choice and never the
  // keyed answer, and an item whose misconception is keyed on the answer itself is rejected.
  add("tutor.choice_diagnosis_never_reveals_key", choiceSelfCheck());

  const ok = checks.every((c) => c.status === "MATCH");
  return { tool: "learn", version, status: ok ? "MATCH" : "DEGRADED", checks };
}
