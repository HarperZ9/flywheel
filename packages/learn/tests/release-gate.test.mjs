// The release gate and workflow. learn 1.6.0 was published by hand from a local machine,
// with no tag, no GitHub Release, no SHA256SUMS and CI actions pinned by moving tags. The gate
// script is what release.yml runs before anything is packed; the workflow checks below catch a
// later edit that drops a gate, a pin or the trusted-publishing setup.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const read = (rel) => readFileSync(join(ROOT, rel), "utf8");
const pkg = JSON.parse(read("package.json"));
const TAG = "v" + pkg.version;
const gate = (...args) => spawnSync(process.execPath, [join(ROOT, "scripts", "check-release.mjs"), ...args], { cwd: ROOT, encoding: "utf8" });

test("the gate passes for the package's own tag and repository", () => {
  const r = gate(TAG, "HarperZ9/learn");
  assert.equal(r.status, 0, r.stdout + r.stderr);
  assert.match(r.stdout, new RegExp(`release gate: ${TAG.replace(/\./g, "\\.")} ok`));
});

test("the gate fails on a tag for another version", () => {
  const r = gate("v0.0.1", "HarperZ9/learn");
  assert.equal(r.status, 1);
  assert.match(r.stdout, /tag v0\.0\.1 does not match/);
});

test("the gate fails when package.json names another repository", () => {
  const r = gate(TAG, "someone/fork");
  assert.equal(r.status, 1);
  assert.match(r.stdout, /repository\.url/);
});

test("the gate writes the CHANGELOG section for the version as release notes", () => {
  const out = join(mkdtempSync(join(tmpdir(), "learn-notes-")), "notes.md");
  const r = gate(TAG, "HarperZ9/learn", "--notes", out);
  assert.equal(r.status, 0, r.stdout + r.stderr);
  const notes = readFileSync(out, "utf8");
  assert.ok(notes.trim().length > 0);
  assert.doesNotMatch(notes, /^## /m, "notes hold one section's body only");
});

const release = read(".github/workflows/release.yml");
const ci = read(".github/workflows/ci.yml");

test("every action in ci.yml and release.yml is pinned to a full commit SHA", () => {
  for (const [name, text] of [["ci.yml", ci], ["release.yml", release]]) {
    const uses = [...text.matchAll(/uses:\s*([^\s#]+)/g)].map((m) => m[1]);
    assert.ok(uses.length > 0, name);
    for (const u of uses) assert.match(u, /@[0-9a-f]{40}$/, `${name}: ${u}`);
  }
});

test("release.yml runs on a v* tag, gates the version and smokes the tarball on three systems", () => {
  assert.match(release, /tags:\s*\[\s*"v\*"\s*\]/);
  assert.match(release, /node scripts\/check-release\.mjs "\$GITHUB_REF_NAME" "\$GITHUB_REPOSITORY"/);
  assert.match(release, /node scripts\/smoke-tarball\.mjs/);
  for (const os of ["ubuntu-latest", "macos-latest", "windows-latest"]) assert.ok(release.includes(os), os);
});

test("release.yml publishes through npm trusted publishing: OIDC only in the publish job, no --provenance flag", () => {
  assert.equal((release.match(/id-token:\s*write/g) || []).length, 1);
  assert.match(release, /npm publish /);
  assert.doesNotMatch(release, /--provenance/);
  assert.doesNotMatch(release, /NPM_TOKEN|NODE_AUTH_TOKEN:/);
  assert.match(release, /node-version:\s*"24"/);
  assert.match(release, /11\.5\.1/);
});

test("release.yml attaches the tarball and SHA256SUMS to a GitHub Release", () => {
  assert.match(release, /gh release create/);
  assert.match(release, /SHA256SUMS/);
});

test("ci.yml packs the tarball and runs it through npx on Windows, Linux and macOS", () => {
  assert.match(ci, /npm pack/);
  assert.match(ci, /node scripts\/smoke-tarball\.mjs/);
  for (const os of ["ubuntu-latest", "macos-latest", "windows-latest"]) assert.ok(ci.includes(os), os);
});
