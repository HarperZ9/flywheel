#!/usr/bin/env node
// A self-contained tour of `learn`, offline, zero-dep, nothing downloaded.
//
// Part 1 (credential engine): load examples/course.json, dry-run it against the FakeDriver, and
// watch it halt at the `assess` step ("Quiz 1") rather than auto-completing the graded work. Then
// resume it with the operator's own attestation and verify the witnessed ledger.
//
// Part 2 (tutor / learning loop): load examples/study.json (an in-progress study session with a
// concept map: power-rule -> product-rule -> chain-rule) and run one turn of the study-loop,
// printing what is due, which objectives are unlocked, and the mastery verdict, all derived
// strictly from the operator's OWN recorded practice attempts in that file.
//
//     node examples/demo.mjs
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

import { loadWorkflow } from "../src/workflow/schema.mjs";
import { run, resume } from "../src/runtime/runner.mjs";
import { FakeDriver } from "../src/actuation/driver.mjs";
import "../src/adapters/fake.mjs";
import { newSession, recordAttempt } from "../src/tutor/tutor.mjs";
import { studyPlan } from "../src/tutor/study.mjs";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const NOW = "2026-06-30T00:00:00.000Z"; // fixed clock so the demo output is stable

function loadJson(name) {
  return JSON.parse(readFileSync(path.join(HERE, name), "utf8"));
}

async function runCredentialEngine() {
  console.log("== learn run: examples/course.json ==");
  const wf = loadWorkflow(loadJson("course.json"));
  console.log(`workflow "${wf.course}" (${wf.adapter} adapter): ${wf.steps.length} steps, seal ${wf.seal.slice(0, 19)}...`);

  const driver = new FakeDriver();
  const first = await run(wf, { driver });
  const haltedStep = wf.steps[first.haltedAt];
  console.log(`status: ${first.status} @ step ${first.haltedAt} (${haltedStep.kind}: "${haltedStep.label}")`);
  console.log("driver actions so far:", driver.actions.join(", ") || "(none)");
  console.log("the engine will not touch the graded step. it waits for the operator.");

  // The operator does the quiz themselves, then attests to it and resumes.
  const done = await resume(wf, {
    driver,
    ledger: first.ledger,
    haltedAt: first.haltedAt,
    humanAttest: { seq: first.haltedAt, note: "completed Quiz 1 myself", at: NOW },
  });
  console.log(`resumed -> status: ${done.status}`);
  const verify = done.ledger.verify();
  console.log(`ledger verify: ${verify.ok ? "chain ok" : "chain BROKEN at " + verify.brokenAt}`);
  if (done.completion) {
    console.log(`completion certificate: ${done.completion.certId}`);
  }
}

async function runTutorStudyLoop() {
  console.log("\n== learn tutor study-loop: examples/study.json ==");
  const data = loadJson("study.json");
  // session.objectives stays plain ids (what mastery()/schedule()/misconceptions() key on); the
  // richer {id, text, requires} concept map is passed separately into studyPlan's `objectives`.
  const session = newSession({ topic: data.topic, objectives: data.sessionObjectives });
  for (const a of data.attempts) {
    recordAttempt(session, a);
  }
  console.log(`topic "${session.topic}": ${session.objectives.length} objective(s), ${session.attempts.length} practice attempt(s) (the operator's own)`);

  const plan = studyPlan(session, { now: NOW, objectives: data.conceptMap });

  console.log(`due (${plan.due.length}): ${plan.due.map((d) => d.objective).join(", ") || "(none)"}`);
  console.log(`misconceptions (${plan.misconceptions.length}): ${plan.misconceptions.map((m) => `${m.objective} (${m.count}x)`).join(", ") || "(none)"}`);
  console.log(`readiness: ${plan.readiness.map((r) => `${r.objective}:${r.unlocked ? "unlocked" : "locked"}`).join(", ")}`);
  console.log(`mastery: ${plan.mastery.ready ? "READY" : "not yet"}`);
  for (const p of plan.mastery.perObjective) {
    console.log(`  [${p.ready ? "ready" : "keep going"}] ${p.objective}: ${p.correct}/${p.attempts} (${Math.round(p.accuracy * 100)}%)`);
  }
  console.log("mastery is a function of the operator's own scored attempts only. nothing here answers the quiz above.");
}

async function main() {
  await runCredentialEngine();
  await runTutorStudyLoop();
}

main().catch((err) => {
  console.error(err);
  process.exitCode = 1;
});
