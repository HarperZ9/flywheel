#!/usr/bin/env node
import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { join, resolve } from "node:path";
import { Ledger } from "./accountability/ledger.mjs";
import { doctor } from "./doctor.mjs";
import { status } from "./status.mjs";
import { stateRoot } from "./state.mjs";
import { LearnError } from "./errors.mjs";
import { runCommand } from "./cli-run.mjs";
import { arg, has } from "./argv.mjs";
import { isMain } from "./entry.mjs";

const USAGE = "usage: learn <run|resume|verify|receipt|doctor|status|assist|tutor|visualize|mcp> ... [--dir <state folder>]";

// State lives in the learn state folder: --dir when given, else LEARN_HOME, else a per-user data
// folder (src/state.mjs). An id that would leave that folder is refused with exit code 1.
export async function main(argv, opts = {}) {
  try {
    return await command(argv, opts);
  } catch (err) {
    if (err instanceof LearnError) return { code: 1, out: `learn: ${err.message}` };
    throw err;
  }
}

async function command(argv, { dir: given } = {}) {
  const [cmd] = argv;
  const dirFlag = arg(argv, "--dir");
  const state = dirFlag ? { dir: resolve(dirFlag), source: "--dir" } : given ? { dir: given, source: "--dir" } : stateRoot();
  const dir = state.dir;
  const engine = await runCommand(cmd, argv, dir);
  if (engine) return engine;
  if (cmd === "doctor") {
    const d = await doctor();
    return { code: d.status === "MATCH" ? 0 : 1, out: `learn doctor: ${d.status}\n` + d.checks.map((c) => `  [${c.status}] ${c.name}`).join("\n") };
  }
  if (cmd === "status") {
    return { code: 0, out: JSON.stringify(status({ state }), null, 2) };
  }
  if (cmd === "tutor") {
    const { newSession, newSessionWithFSRS, recordAttempt, recordAttemptWithGrade, mastery, masteryReceipt } = await import("./tutor/tutor.mjs");
    const { saveSession, loadSession, sessionExists, writeSessionFile } = await import("./tutor/tutorstore.mjs");
    const sub = argv[1]; const id = argv[2];
    if (sub === "plan") {
      const objectives = (arg(argv, "--objectives") || "").split(",").map((x) => x.trim()).filter(Boolean);
      const topic = arg(argv, "--topic") || "";
      // --enable-fsrs seeds per-item FSRS scheduling state (opt-in; default sessions are unchanged).
      if (sessionExists(dir, id) && !has(argv, "--replace")) {
        return { code: 1, out: `tutor plan ${id}: a session with that id already exists; pass --replace to start it over` };
      }
      const s = has(argv, "--enable-fsrs") ? newSessionWithFSRS({ topic, objectives }) : newSession({ topic, objectives });
      saveSession(dir, id, s);
      const fsrsNote = has(argv, "--enable-fsrs") ? " (FSRS scheduling enabled)" : "";
      return { code: 0, out: `tutor plan ${id}: ${s.objectives.length} objective(s)${fsrsNote}` };
    }
    if (sub === "record") {
      const s = loadSession(dir, id); if (!s) return { code: 1, out: `no tutor session: ${id}` };
      const gradeRaw = arg(argv, "--grade");
      const now = arg(argv, "--now");
      const common = { objective: arg(argv, "--objective"), prompt: arg(argv, "--prompt") || "", answer: arg(argv, "--answer") || "", feedback: arg(argv, "--feedback") || "" };
      // --grade (0-4) + --now routes through the FSRS-aware path (logs the attempt AND updates the
      // per-item scheduling state). Without --grade, the plain correct/incorrect record path is used.
      if (gradeRaw !== undefined && gradeRaw !== null) {
        if (!now) return { code: 1, out: "tutor record: --now is required when --grade is given (ISO string or epoch ms)" };
        const grade = Number(gradeRaw);
        if (!Number.isInteger(grade) || grade < 0 || grade > 4) return { code: 1, out: "tutor record: --grade must be an integer 0-4 (0=fail,1=slip,2=lapse,3=review,4=easy)" };
        recordAttemptWithGrade(s, { ...common, grade, correct: has(argv, "--correct") ? arg(argv, "--correct") === "true" : undefined, now });
      } else {
        recordAttempt(s, { ...common, correct: arg(argv, "--correct") === "true" });
      }
      saveSession(dir, id, s);
      return { code: 0, out: `tutor record ${id}: ${s.attempts.length} practice attempt(s)` };
    }
    if (sub === "mastery") {
      const s = loadSession(dir, id); if (!s) return { code: 1, out: `no tutor session: ${id}` };
      const m = mastery(s, { threshold: Number(arg(argv, "--threshold")) || 0.8, minAttempts: Number(arg(argv, "--min")) || 3 });
      return { code: m.ready ? 0 : 1, out: `tutor mastery ${id}: ${m.ready ? "READY" : "not yet"}\n` + m.perObjective.map((p) => `  [${p.ready ? "ready" : "keep going"}] ${p.objective}: ${p.correct}/${p.attempts} (${Math.round(p.accuracy * 100)}%)`).join("\n") };
    }
    if (sub === "receipt") {
      const s = loadSession(dir, id); if (!s) return { code: 1, out: `no tutor session: ${id}` };
      const r = masteryReceipt(s);
      writeSessionFile(dir, id, ".mastery.json", JSON.stringify(r, null, 2));
      return { code: 0, out: `tutor receipt ${id}: mastery ${r.mastery.ready ? "READY" : "not yet"}, ${r.totalAttempts} attempts -> tutor/${id}.mastery.json` };
    }
    if (sub === "due") {
      const s = loadSession(dir, id); if (!s) return { code: 1, out: `no tutor session: ${id}` };
      const { due } = await import("./tutor/schedule.mjs");
      const now = arg(argv, "--now"); if (!now) return { code: 1, out: "tutor due: --now is required (ISO string or epoch ms)" };
      const useFSRS = has(argv, "--use-fsrs");
      const desiredRetention = arg(argv, "--desired-retention") ? Number(arg(argv, "--desired-retention")) : 0.9;
      const list = due(s, { now, asOf: arg(argv, "--as-of") || undefined, useFSRS, desiredRetention });
      return { code: 0, out: `tutor due ${id}: ${list.length} objective(s) due\n` + list.map((d) => `  ${d.objective} (overdue since ${d.dueAt})`).join("\n") };
    }
    if (sub === "misconceptions") {
      const s = loadSession(dir, id); if (!s) return { code: 1, out: `no tutor session: ${id}` };
      const { misconceptions } = await import("./tutor/misconception.mjs");
      const list = misconceptions(s);
      return { code: 0, out: `tutor misconceptions ${id}: ${list.length} objective(s)\n` + list.map((m) => `  ${m.objective} (${m.count}x): ${m.notes.join("; ")}` +
        (m.diagnoses ? `\n    causes: ${Object.entries(m.diagnoses).map(([k, v]) => `${k} ${v}`).join(", ")}` : "")).join("\n") };
    }
    if (sub === "retrieval") {
      const s = loadSession(dir, id); if (!s) return { code: 1, out: `no tutor session: ${id}` };
      const { clozePrompts } = await import("./tutor/retrieval.mjs");
      const { assist } = await import("./assist/assist.mjs");
      const draftPath = arg(argv, "--draft"); if (!draftPath) return { code: 1, out: "tutor retrieval: --draft <file> is required" };
      const draft = readFileSync(draftPath, "utf8");
      const a = assist(draft);
      const prompts = clozePrompts(a, { objective: arg(argv, "--objective") || null });
      return { code: 0, out: `tutor retrieval ${id}: ${prompts.length} cloze prompt(s)\n` + prompts.map((p) => `  ${p.prompt}  [source: ${p.source || "n/a"}]`).join("\n") };
    }
    if (sub === "explain") {
      const s = loadSession(dir, id); if (!s) return { code: 1, out: `no tutor session: ${id}` };
      const { explanationThesis } = await import("./tutor/explain.mjs");
      const filePath = arg(argv, "--file"); if (!filePath) return { code: 1, out: "tutor explain: --file <file> is required" };
      const explanation = readFileSync(filePath, "utf8");
      const thesis = explanationThesis(explanation);
      writeSessionFile(dir, id, ".explain-thesis.json", JSON.stringify(thesis, null, 2));
      return { code: 0, out: `tutor explain ${id}: thesis with ${thesis.claims.length} claim(s) -> tutor/${id}.explain-thesis.json` };
    }
    if (sub === "predict") {
      const s = loadSession(dir, id); if (!s) return { code: 1, out: `no tutor session: ${id}` };
      const { recordPrediction } = await import("./tutor/predict.mjs");
      recordPrediction(s, { objective: arg(argv, "--objective"), prompt: arg(argv, "--prompt") || "", prediction: arg(argv, "--prediction") || "" });
      saveSession(dir, id, s);
      return { code: 0, out: `tutor predict ${id}: prediction recorded as pending attempt ${s.attempts.length - 1}` };
    }
    if (sub === "score") {
      const s = loadSession(dir, id); if (!s) return { code: 1, out: `no tutor session: ${id}` };
      const { scorePrediction } = await import("./tutor/predict.mjs");
      const index = Number(arg(argv, "--index"));
      scorePrediction(s, { index, correct: arg(argv, "--correct") === "true", note: arg(argv, "--note") || "" });
      saveSession(dir, id, s);
      return { code: 0, out: `tutor score ${id}: attempt ${index} scored` };
    }
    if (sub === "path") {
      const s = loadSession(dir, id); if (!s) return { code: 1, out: `no tutor session: ${id}` };
      const { learningPath } = await import("./tutor/map.mjs");
      const path = learningPath(s.objectives);
      return { code: 0, out: `tutor path ${id}: ${path.join(" -> ")}` };
    }
    if (sub === "study") {
      const s = loadSession(dir, id); if (!s) return { code: 1, out: `no tutor session: ${id}` };
      const { studyPlan } = await import("./tutor/study.mjs");
      const now = arg(argv, "--now"); if (!now) return { code: 1, out: "tutor study: --now is required (ISO string or epoch ms)" };
      const useFSRS = has(argv, "--use-fsrs");
      const desiredRetention = arg(argv, "--desired-retention") ? Number(arg(argv, "--desired-retention")) : 0.9;
      const plan = studyPlan(s, { now, seed: arg(argv, "--seed") || undefined, useFSRS, desiredRetention });
      return { code: 0, out: `tutor study ${id}: ${plan.due.length} due, ${plan.misconceptions.length} misconception(s), mastery ${plan.mastery.ready ? "READY" : "not yet"}\n` +
        `  due: ${plan.due.map((d) => d.objective).join(", ") || "(none)"}\n` +
        `  order: ${plan.order.join(", ")}\n` +
        `  readiness: ${plan.readiness.map((r) => `${r.objective}:${r.unlocked ? "unlocked" : "locked"}`).join(", ")}` };
    }
    if (sub === "prooflesson") {
      const { proofLessonReceipt } = await import("./tutor/prooflesson.mjs");
      const packetPath = arg(argv, "--packet"); if (!packetPath) return { code: 1, out: "tutor prooflesson: --packet <packet.json> is required" };
      let receipt;
      try { receipt = proofLessonReceipt(JSON.parse(readFileSync(packetPath, "utf8"))); }
      catch (e) { return { code: 1, out: `tutor prooflesson ${id}: packet rejected: ${(e && e.message) || e}` }; }
      writeSessionFile(dir, id, ".prooflesson.json", JSON.stringify(receipt, null, 2));
      const misc = receipt.misconception ? `, misconception ${receipt.misconception.misconception_class}` : "";
      return { code: 0, out: `tutor prooflesson ${id}: verdict ${receipt.verdict}, ${receipt.lesson.scaffold.length} scaffold step(s), ${receipt.lesson.retrievalQuestions.length} question(s)${misc} -> tutor/${id}.prooflesson.json` };
    }
    if (sub === "reverify") {
      const { reverifyFiles, formatReverify } = await import("./tutor/reverify.mjs");
      const file = arg(argv, "--file");
      const r = reverifyFiles(dir, id, { file });
      return { code: r.ok ? 0 : 1, out: formatReverify(r, file || id) };
    }
    if (sub === "study-receipt") {
      const s = loadSession(dir, id); if (!s) return { code: 1, out: `no tutor session: ${id}` };
      const { studyReceipt } = await import("./tutor/study.mjs");
      const now = arg(argv, "--now"); if (!now) return { code: 1, out: "tutor study-receipt: --now is required (ISO string or epoch ms)" };
      const useFSRS = has(argv, "--use-fsrs");
      const desiredRetention = arg(argv, "--desired-retention") ? Number(arg(argv, "--desired-retention")) : 0.9;
      const r = studyReceipt(s, { now, seed: arg(argv, "--seed") || undefined, useFSRS, desiredRetention });
      writeSessionFile(dir, id, ".study-receipt.json", JSON.stringify(r, null, 2));
      return { code: 0, out: `tutor study-receipt ${id}: verified ${r.verified}, mastery ${r.mastery.ready ? "READY" : "not yet"} -> tutor/${id}.study-receipt.json` };
    }
    if (sub === "derive-schedule") {
      const s = loadSession(dir, id); if (!s) return { code: 1, out: `no tutor session: ${id}` };
      const { deriveScheduleReceipt } = await import("./tutor/fsrsderive.mjs");
      const r = deriveScheduleReceipt(s, { optimize: has(argv, "--optimize") });
      writeSessionFile(dir, id, ".derive-schedule.json", JSON.stringify(r, null, 2));
      const drift = r.perObjective.filter((p) => !p.match).map((p) => p.objective);
      const driftNote = drift.length ? `\n  DRIFT on: ${drift.join(", ")} (the cached hint differs from the recorded log; learn uses the log)` : "";
      return {
        code: r.verdict === "DRIFT" ? 1 : 0,
        out: `tutor derive-schedule ${id}: verdict ${r.verdict}, re-derived ${r.fsrsAttempts} graded attempt(s), ledger ${r.ledgerVerified ? "verified" : "BROKEN"} -> tutor/${id}.derive-schedule.json${driftNote}`,
      };
    }
    return { code: 1, out: "usage: learn tutor <plan|record|mastery|receipt|reverify|prooflesson|due|misconceptions|retrieval|explain|predict|score|path|study|study-receipt|derive-schedule> <id> ..." };
  }
  if (cmd === "assist") {
    const { assistArtifacts } = await import("./assist/assist.mjs");
    const draft = readFileSync(argv[1], "utf8");
    const out = resolve(arg(argv, "--out") || join(dir, "assist"));
    mkdirSync(out, { recursive: true });
    const art = assistArtifacts(draft, { title: arg(argv, "--title") || undefined });
    writeFileSync(join(out, "assist.json"), JSON.stringify(art.assist, null, 2));
    writeFileSync(join(out, "crucible-thesis.json"), JSON.stringify(art.crucibleThesis, null, 2));
    writeFileSync(join(out, "gather-manifest.json"), JSON.stringify(art.gatherManifest, null, 2));
    let extra = "";
    if (has(argv, "--crucible")) {
      const { crucibleAssess } = await import("./interop/crucible.mjs");
      const r = await crucibleAssess(join(out, "crucible-thesis.json"));
      extra += `\ncrucible: ${r.ran ? ("ran (exit " + r.code + ")") : r.reason}`;
    }
    if (has(argv, "--gather")) {
      const { gatherRun } = await import("./interop/gather.mjs");
      const r = await gatherRun(art.gatherManifest.sources);
      extra += `\ngather: ${r.ran ? (r.receipts.length + " source(s) processed") : r.reason}`;
    }
    return { code: 0, out: `assist: ${art.assist.claims.length} claim(s) + ${art.assist.sources.length} source(s) -> ${out}/{assist,crucible-thesis,gather-manifest}.json (authors nothing — flags what YOU verify)${extra}` };
  }
  if (cmd === "visualize") {
    const { toTelosSceneSpec, telosRender, toAidLedgerEntry } = await import("./interop/telos.mjs");
    const concept = JSON.parse(readFileSync(argv[1], "utf8"));
    const out = resolve(arg(argv, "--out") || join(dir, "runs"));
    mkdirSync(out, { recursive: true });
    const spec = toTelosSceneSpec(concept);
    const specPath = join(out, "scene-request.json");
    writeFileSync(specPath, JSON.stringify(spec, null, 2));
    const render = await telosRender(specPath);
    const ledger = new Ledger();
    ledger.append(toAidLedgerEntry(render, { concept, seq: 0 }));
    const slug = (spec.concept.title || "concept").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "") || "concept";
    const aidReceipt = { provenance: "aid", concept: spec.concept, request: spec, render, ledger: ledger.entries(), verified: ledger.verify().ok,
      note: "Learning aid — this render never satisfies graded work; the operator still does every assessment." };
    writeFileSync(join(out, slug + ".aid.json"), JSON.stringify(aidReceipt, null, 2));
    return { code: 0, out: `visualize: ${spec.concept.title || "(concept)"} -> ${render.verdict}${render.selected_profile ? " (profile " + render.selected_profile + ")" : ""}, provenance aid -> ${out}/${slug}.aid.json` };
  }
  return { code: 1, out: USAGE };
}

// Program start: `learn ...` through npm's bin, or `node src/cli.mjs ...`. `learn mcp` hands
// stdin and stdout to the MCP server and prints nothing of its own.
if (isMain(import.meta.url)) {
  const argv = process.argv.slice(2);
  if (argv[0] === "mcp") {
    const { serve } = await import("./mcp.mjs");
    const dirFlag = arg(argv, "--dir");
    serve(dirFlag ? { dir: resolve(dirFlag) } : {});
  } else {
    main(argv).then(
      (r) => process.stdout.write(r.out + "\n", () => process.exit(r.code)),
      (err) => { process.stderr.write(`learn: ${(err && err.stack) || err}\n`); process.exit(1); },
    );
  }
}
