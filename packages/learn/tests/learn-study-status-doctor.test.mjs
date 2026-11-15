import { test } from "node:test";
import assert from "node:assert/strict";
import { doctor } from "../src/doctor.mjs";
import { status } from "../src/status.mjs";
import { version } from "../src/index.mjs";

test("version is bumped to 2.3.0", () => {
  assert.equal(version, "2.3.0");
});

test("status describes the learning loop (schedule/misconception/retrieval/explain/predict/map/study) under a dedicated field", () => {
  const s = status();
  assert.ok(s.learningLoop, "status must describe the learning loop under a new field");
  const serialized = JSON.stringify(s.learningLoop);
  assert.match(serialized, /spac|schedul/i);
  assert.match(serialized, /misconcep/i);
  assert.match(serialized, /retriev|cloze/i);
  assert.match(serialized, /predict/i);
  assert.match(serialized, /explain|self-explan/i);
  assert.match(serialized, /prerequisite|readiness|path/i);
});

test("doctor: mastery stays MATCH independent of visualizations/predictions (render/visualization-independence check)", async () => {
  const d = await doctor();
  assert.equal(d.status, "MATCH");
  const check = d.checks.find((c) => /mastery.*(render|visuali)|((render|visuali)).*mastery/i.test(c.name));
  assert.ok(check, "doctor must include a mastery render/visualization-independence check");
  assert.equal(check.status, "MATCH");
});
