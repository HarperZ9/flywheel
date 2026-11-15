import { test } from "node:test";
import assert from "node:assert/strict";
import { newSession, recordAttempt, mastery } from "../src/tutor/tutor.mjs";
import { normalizeObjectives, learningPath, readiness } from "../src/tutor/map.mjs";

test("normalizeObjectives: a plain string objective normalizes to {id, text, requires:[]}", () => {
  const norm = normalizeObjectives(["addition", "subtraction"]);
  assert.deepEqual(norm, [
    { id: "addition", text: "addition", requires: [] },
    { id: "subtraction", text: "subtraction", requires: [] },
  ]);
});

test("normalizeObjectives: an object objective is passed through with requires defaulted to []", () => {
  const norm = normalizeObjectives([{ id: "calc", text: "Calculus" }]);
  assert.deepEqual(norm, [{ id: "calc", text: "Calculus", requires: [] }]);
});

test("normalizeObjectives: an object objective with requires is preserved", () => {
  const norm = normalizeObjectives([
    { id: "algebra", text: "Algebra" },
    { id: "calc", text: "Calculus", requires: ["algebra"] },
  ]);
  assert.deepEqual(norm[1].requires, ["algebra"]);
});

test("normalizeObjectives: mixed strings and objects in the same list", () => {
  const norm = normalizeObjectives(["algebra", { id: "calc", text: "Calculus", requires: ["algebra"] }]);
  assert.equal(norm.length, 2);
  assert.deepEqual(norm[0], { id: "algebra", text: "algebra", requires: [] });
  assert.equal(norm[1].id, "calc");
});

test("normalizeObjectives: backward compatible — a session built with plain string objectives is untouched by existing tutor tests", () => {
  const s = newSession({ topic: "SC-900", objectives: ["identity", "compliance"] });
  recordAttempt(s, { objective: "identity", prompt: "q1", answer: "a1", correct: true });
  recordAttempt(s, { objective: "identity", prompt: "q2", answer: "a2", correct: true });
  recordAttempt(s, { objective: "identity", prompt: "q3", answer: "a3", correct: true });
  recordAttempt(s, { objective: "compliance", prompt: "q1", answer: "a1", correct: true });
  const m = mastery(s, { threshold: 0.8, minAttempts: 3 });
  assert.equal(m.ready, false);
  assert.deepEqual(m.weakest, ["compliance"]);
  // map.mjs normalization is purely additive; it must not change mastery's own identity reads.
  const norm = normalizeObjectives(s.objectives);
  assert.deepEqual(norm.map((o) => o.id), ["identity", "compliance"]);
});

test("learningPath: topologically orders ids so a prerequisite always precedes its dependent", () => {
  const objectives = [
    { id: "algebra", text: "Algebra" },
    { id: "calc", text: "Calculus", requires: ["algebra"] },
    { id: "physics", text: "Physics", requires: ["calc"] },
  ];
  const path = learningPath(objectives);
  assert.deepEqual(path, ["algebra", "calc", "physics"]);
});

test("learningPath: independent objectives with no requires keep a stable, deterministic order", () => {
  const objectives = ["a", "b", "c"];
  const path = learningPath(objectives);
  assert.deepEqual(path, ["a", "b", "c"]);
});

test("learningPath: a diamond dependency resolves consistently (each id appears exactly once)", () => {
  const objectives = [
    { id: "root", text: "Root" },
    { id: "left", text: "Left", requires: ["root"] },
    { id: "right", text: "Right", requires: ["root"] },
    { id: "join", text: "Join", requires: ["left", "right"] },
  ];
  const path = learningPath(objectives);
  assert.equal(path.length, 4);
  assert.ok(path.indexOf("root") < path.indexOf("left"));
  assert.ok(path.indexOf("root") < path.indexOf("right"));
  assert.ok(path.indexOf("left") < path.indexOf("join"));
  assert.ok(path.indexOf("right") < path.indexOf("join"));
});

test("learningPath: throws on a cycle rather than silently returning a partial/incorrect order", () => {
  const objectives = [
    { id: "a", text: "A", requires: ["b"] },
    { id: "b", text: "B", requires: ["a"] },
  ];
  assert.throws(() => learningPath(objectives), /cycle/i);
});

test("learningPath: throws on a self-referencing objective (degenerate 1-node cycle)", () => {
  const objectives = [{ id: "a", text: "A", requires: ["a"] }];
  assert.throws(() => learningPath(objectives), /cycle/i);
});

test("learningPath: throws on a longer cycle (3-node)", () => {
  const objectives = [
    { id: "a", text: "A", requires: ["c"] },
    { id: "b", text: "B", requires: ["a"] },
    { id: "c", text: "C", requires: ["b"] },
  ];
  assert.throws(() => learningPath(objectives), /cycle/i);
});

test("readiness: an objective with no requires is always unlocked", () => {
  const s = newSession({ topic: "t", objectives: ["algebra"] });
  const m = mastery(s, { threshold: 0.8, minAttempts: 1 });
  const r = readiness(s, ["algebra"], m);
  assert.equal(r.find((x) => x.objective === "algebra").unlocked, true);
});

test("readiness: an objective is unlocked only once ALL its requires are mastered (ready:true in mastery's perObjective)", () => {
  const s = newSession({ topic: "t", objectives: ["algebra", "calc"] });
  recordAttempt(s, { objective: "algebra", prompt: "q", answer: "x", correct: true });
  recordAttempt(s, { objective: "algebra", prompt: "q2", answer: "x", correct: true });
  recordAttempt(s, { objective: "algebra", prompt: "q3", answer: "x", correct: true });
  // calc not attempted at all yet
  const objectives = [
    { id: "algebra", text: "Algebra" },
    { id: "calc", text: "Calculus", requires: ["algebra"] },
  ];
  const m = mastery(s, { threshold: 0.8, minAttempts: 3 });
  const r = readiness(s, objectives, m);
  assert.equal(r.find((x) => x.objective === "algebra").unlocked, true);
  assert.equal(r.find((x) => x.objective === "calc").unlocked, true, "algebra is mastered, so calc unlocks");
});

test("readiness: an objective stays locked while any of its requires is not yet mastered", () => {
  const s = newSession({ topic: "t", objectives: ["algebra", "calc"] });
  recordAttempt(s, { objective: "algebra", prompt: "q", answer: "x", correct: false }); // not mastered
  const objectives = [
    { id: "algebra", text: "Algebra" },
    { id: "calc", text: "Calculus", requires: ["algebra"] },
  ];
  const m = mastery(s, { threshold: 0.8, minAttempts: 3 });
  const r = readiness(s, objectives, m);
  // algebra itself has no requires, so it is always unlocked (available to study); it is simply
  // not yet MASTERED (see m.perObjective). calc requires algebra's mastery, so it stays locked.
  assert.equal(r.find((x) => x.objective === "algebra").unlocked, true);
  assert.equal(r.find((x) => x.objective === "calc").unlocked, false);
});

test("readiness: a multi-prereq objective needs ALL requires mastered, not just one", () => {
  const s = newSession({ topic: "t", objectives: ["left", "right", "join"] });
  for (let i = 0; i < 3; i++) recordAttempt(s, { objective: "left", prompt: "q" + i, answer: "x", correct: true });
  // right: never attempted -> not mastered
  const objectives = [
    { id: "left", text: "Left" },
    { id: "right", text: "Right" },
    { id: "join", text: "Join", requires: ["left", "right"] },
  ];
  const m = mastery(s, { threshold: 0.8, minAttempts: 3 });
  const r = readiness(s, objectives, m);
  assert.equal(r.find((x) => x.objective === "join").unlocked, false);
});

test("readiness: works with plain string objectives (no requires) end-to-end via mastery()", () => {
  const s = newSession({ topic: "t", objectives: ["a", "b"] });
  recordAttempt(s, { objective: "a", prompt: "q", answer: "x", correct: true });
  const m = mastery(s, { threshold: 0.8, minAttempts: 1 });
  const r = readiness(s, ["a", "b"], m);
  assert.equal(r.length, 2);
  assert.ok(r.every((x) => x.unlocked === true));
});
