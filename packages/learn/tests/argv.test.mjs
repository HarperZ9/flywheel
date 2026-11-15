// One parse of the command line. The 2.0.0 candidate found grants and switches with
// argv.includes, so a grant word given as the value of another flag (an attestation note, an id,
// a topic) still counted. A flag that takes a value now consumes the next token, and a switch
// counts only where a flag can stand. The behavior tests are in security-resume.test.mjs and
// security-path-escape.test.mjs; these pin the parser and keep the CLI on it.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { parseArgv, arg, has, VALUE_FLAGS } from "../src/argv.mjs";

const SRC = (name) => readFileSync(fileURLToPath(new URL(`../src/${name}`, import.meta.url)), "utf8");
const CLI_FILES = ["cli.mjs", "cli-run.mjs"];

test("a value flag consumes the next token, so a grant word there is a value and not a grant", () => {
  const argv = ["resume", "r1", "--attest", "--allow-cost", "--url", "--native", "--submit", "manual"];
  const p = parseArgv(argv);
  assert.equal(p.values.get("--attest"), "--allow-cost");
  assert.equal(p.values.get("--url"), "--native");
  assert.equal(has(argv, "--allow-cost"), false);
  assert.equal(has(argv, "--native"), false);
  assert.equal(arg(argv, "--submit"), "manual");
  assert.deepEqual(p.positionals, ["resume", "r1"]);
});

test("switches count in flag position; the first value of a repeated flag wins; a missing value is undefined", () => {
  const argv = ["resume", "r1", "--allow-cost", "--attest", "a", "--attest", "b", "--id"];
  assert.equal(has(argv, "--allow-cost"), true);
  assert.equal(arg(argv, "--attest"), "a");
  assert.equal(has(argv, "--id"), true);
  assert.equal(arg(argv, "--id"), undefined);
  assert.equal(arg(argv, "--dir"), null, "an absent value flag reads as null");
});

test("reading an unregistered value flag is a programming error, not a silent null", () => {
  assert.throws(() => arg(["x"], "--not-a-flag"), /not a registered value flag/);
});

test("every flag the CLI reads a value from is registered, and no CLI file scans the whole argv", () => {
  for (const file of CLI_FILES) {
    const text = SRC(file);
    for (const [, flag] of text.matchAll(/\barg\(argv, "(--[a-z-]+)"\)/g)) {
      assert.ok(VALUE_FLAGS.has(flag), `${file} reads ${flag} with arg() but it is not in VALUE_FLAGS`);
    }
    assert.doesNotMatch(text, /argv\.(includes|indexOf)\(/, `${file} scans the whole argv; use has() or arg() from src/argv.mjs`);
  }
});
