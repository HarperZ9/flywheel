// Flagship-parity docs/brand/CI test — asserts learn ships the same documentation, brand, and CI
// surface as the other Project Telos flagships (gather/crucible/forum/index/telos), and that the
// integrity line (assess never auto-completes, mastery is practice-only) is stated in the new docs.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const read = (rel) => readFileSync(path.join(ROOT, rel), "utf8");
const exists = (rel) => existsSync(path.join(ROOT, rel));

test("flagship docs set exists: ARCHITECTURE, HOW-IT-WORKS, USAGE, ENTERPRISE-READINESS", () => {
  for (const rel of [
    "docs/ARCHITECTURE.md",
    "docs/HOW-IT-WORKS.md",
    "USAGE.md",
    "docs/ENTERPRISE-READINESS.md",
  ]) {
    assert.ok(exists(rel), `missing ${rel}`);
  }
});

test("docs/ARCHITECTURE.md names the accountability spine and the learning-loop modules", () => {
  const arch = read("docs/ARCHITECTURE.md");
  for (const needle of [
    "gate", "ledger", "witness",
    "schedule", "misconception", "retrieval", "explain", "predict", "map", "study",
    "mastery",
  ]) {
    assert.ok(arch.toLowerCase().includes(needle), `ARCHITECTURE.md missing "${needle}"`);
  }
});

test("docs/HOW-IT-WORKS.md walks the study loop in order", () => {
  const how = read("docs/HOW-IT-WORKS.md");
  const steps = ["plan", "due", "retrieval", "predict", "observe", "self-explan", "misconception", "mastery-gate", "receipt"];
  let cursor = -1;
  for (const step of steps) {
    const idx = how.toLowerCase().indexOf(step);
    assert.ok(idx !== -1, `HOW-IT-WORKS.md missing step "${step}"`);
    assert.ok(idx > cursor, `HOW-IT-WORKS.md step "${step}" out of order`);
    cursor = idx;
  }
});

test("USAGE.md documents install and basic usage", () => {
  const usage = read("USAGE.md");
  assert.match(usage, /npm install|node src\/cli\.mjs/);
  assert.match(usage, /tutor plan/);
  assert.match(usage, /tutor study/);
});

test("docs/ENTERPRISE-READINESS.md aligns with Project Telos context envelopes and action receipts", () => {
  const er = read("docs/ENTERPRISE-READINESS.md");
  assert.match(er, /context envelope/i);
  assert.match(er, /action receipt/i);
  assert.match(er, /assess/i);
});

test("flagship brand assets exist and are referenced from README", () => {
  const readme = read("README.md");
  for (const rel of [
    "docs/art/hero-light.svg",
    "docs/art/hero-dark.svg",
    "docs/brand/mark-tile.svg",
    "docs/art/social.png",
    "docs/brand/README.md",
  ]) {
    assert.ok(exists(rel), `missing ${rel}`);
  }
  assert.match(readme, /docs\/art\/hero-light\.svg/);
  assert.match(readme, /docs\/art\/hero-dark\.svg/);
});

// 4 October 2026: the brand moved to the shared art direction. The hero and the mark sit on the
// site's grounds (bone #f1ece1 for light, void #040405 for dark), and the iris accent is retired:
// colour is reserved for verdicts and the spectrum for the art's one flare.
test("brand hero SVG is accessible and on-brand (shared grounds, title/desc)", () => {
  for (const [rel, ground] of [["docs/art/hero-light.svg", /#f1ece1/i], ["docs/art/hero-dark.svg", /#040405/i]]) {
    const hero = read(rel);
    assert.match(hero, /<title>[^<]+<\/title><desc>[^<]+<\/desc>/);
    assert.match(hero, /role="img"/);
    assert.match(hero, ground);
    assert.doesNotMatch(hero, /#3a2bd6/i);
    assert.match(hero, /viewBox="0 0 1280 480"/);
  }
});

test("brand mark SVG is accessible and on-brand (shared grounds, title/desc)", () => {
  const mark = read("docs/brand/mark-tile.svg");
  assert.match(mark, /<title>[^<]+<\/title><desc>[^<]+<\/desc>/);
  assert.match(mark, /role="img"/);
  assert.match(mark, /#040405/i);
  assert.doesNotMatch(mark, /#3a2bd6/i);
  assert.match(mark, /viewBox="0 0 512 512"/);
});

test("docs/brand/README.md carries a provenance note (what rendered it, accessibility floor)", () => {
  const brandReadme = read("docs/brand/README.md");
  assert.match(brandReadme, /rendered|renderer/i);
  assert.match(brandReadme, /accessibility/i);
  assert.match(brandReadme, /learn-hero\.png/);
});

test("CI workflow runs node --test on node 20/22 across ubuntu/macos/windows", () => {
  assert.ok(exists(".github/workflows/ci.yml"));
  const ci = read(".github/workflows/ci.yml");
  assert.match(ci, /node --test/);
  assert.match(ci, /20/);
  assert.match(ci, /22/);
  assert.match(ci, /ubuntu-latest/);
  assert.match(ci, /macos-latest/);
  assert.match(ci, /windows-latest/);
});

test("FUNDING.yml points at the operator's github", () => {
  assert.ok(exists(".github/FUNDING.yml"));
  const funding = read(".github/FUNDING.yml");
  assert.match(funding, /github:\s*HarperZ9/);
});

test("no em-dashes in the new docs surface", () => {
  const files = [
    "docs/ARCHITECTURE.md",
    "docs/HOW-IT-WORKS.md",
    "USAGE.md",
    "docs/ENTERPRISE-READINESS.md",
    "docs/brand/README.md",
  ];
  for (const rel of files) {
    const content = read(rel);
    assert.ok(!content.includes("—"), `${rel} contains an em-dash`);
  }
});
