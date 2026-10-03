#!/usr/bin/env node
// audit-mods: scan installed Claude Code plugins for mods that approve tool
// calls or speak for the user, and report them. Read-only: it reads files and
// prints a report. It never changes, disables or uninstalls anything.
//
//   node scripts/audit-mods.mjs [root ...] [--json]
//
// Roots default to ~/.claude/plugins plus every directory in
// CLAUDE_CODE_PLUGIN_DIRS. Exit status: 1 when a HIGH finding exists, else 0.
//
// What it looks for, in each hooks module named by a hooks/hooks.json
// "modules" key and in the module's own relative imports:
//   HIGH   approve-at-check     a tool.check hook (or "*") returns decision "allow"
//   HIGH   classic-allow        a classic.PermissionRequest / classic.PreToolUse
//                               hook returns behavior or permissionDecision "allow"
//   HIGH   forged-consent       code sets `consent:` (a tool call replayed as if
//                               the user pressed Yes)
//   MEDIUM dynamic-decision     a tool.check hook returns { decision: <expression> }
//   MEDIUM answers-tool-call    a tool.call hook returns { result } without running
//                               the tool (no permission prompt appears)
//   MEDIUM speaks-as-user       $.prompt.submit({ asUser: true })
//   MEDIUM skips-tiers          next.to(...): skips later mods
//   INFO   watches-other-mods   plugin.register, engine.create, or a mods-API event
//   INFO   unreadable-event     on() with a non-literal event name
// Static reading only. A clean report is not proof that a mod never approves.

import { readFileSync, readdirSync, statSync, existsSync } from "node:fs";
import { join, dirname, resolve } from "node:path";
import { homedir } from "node:os";
import { pathToFileURL } from "node:url";
import { stripComments, findRegistrations, constString, relativeImports } from "./lib/js-scan.mjs";

const SKIP_DIRS = new Set(["node_modules", ".git", ".flywheel-src", "screenshots"]);
const API_EVENTS = /^(fs|process|http|model|store|env|settings|mcp|tool|prompt|session|ui|command|agent|clock|config|turn|audio|state)\.[a-z]+$/;
// Events Claude Code itself fires (mods reference, read 2026-10-02). A hook on
// one of these is ordinary. A hook on any other namespace.method name intercepts
// other mods' mods-API calls.
const CORE_EVENTS = new Set(("tool.call tool.check tool.describe prompt.submit prompt.fill prompt.suggest " +
  "prompt.edit prompt.compose prompt.section prompt.context prompt.attachment skill.prompt attribution.text " +
  "command.run command.describe config.set config.describe turn.start turn.step turn.complete session.start " +
  "session.end session.compact session.receive session.send session.append session.attach session.detach " +
  "session.measure agent.offer agent.spawn ui.render ui.resolve ui.press ui.input ui.select ui.focus ui.scroll " +
  "ui.close ui.message telemetry.log telemetry.mark").split(" "));

/** Every hooks/hooks.json under a root, to a fixed depth. */
export function findHooksFiles(root, depth = 9) {
  const found = [];
  const walk = (dir, d) => {
    let entries;
    try { entries = readdirSync(dir, { withFileTypes: true }); } catch { return; }
    for (const ent of entries) {
      if (ent.isDirectory()) {
        if (SKIP_DIRS.has(ent.name) || d >= depth) continue;
        const sub = join(dir, ent.name);
        if (ent.name === "hooks" && existsSync(join(sub, "hooks.json"))) found.push(join(sub, "hooks.json"));
        walk(sub, d + 1);
      }
    }
  };
  walk(root, 0);
  return found;
}

/** The module files a hooks.json names, plus their relative imports, recursively. */
export function moduleFiles(hooksJson) {
  let spec;
  try { spec = JSON.parse(readFileSync(hooksJson, "utf8")); } catch { return { files: [], error: "hooks.json is not JSON" }; }
  if (!Array.isArray(spec.modules)) return { files: [] };
  const seen = new Set();
  const queue = spec.modules.map((m) => resolve(dirname(hooksJson), m));
  while (queue.length) {
    const f = queue.shift();
    if (seen.has(f) || !existsSync(f) || !statSync(f).isFile()) continue;
    seen.add(f);
    const code = stripComments(readFileSync(f, "utf8"));
    for (const rel of relativeImports(code)) queue.push(resolve(dirname(f), rel));
  }
  return { files: [...seen] };
}

function isAllow(code, valueSrc) {
  const v = valueSrc.trim();
  if (/^(['"`])allow\1/.test(v)) return "literal";
  const ident = /^[A-Za-z_$][\w$]*/.exec(v);
  if (ident && constString(code, ident[0]) === "allow") return "constant";
  if (ident || /^[\w$.(\[]/.test(v)) return "dynamic";
  return null;
}

/** Findings for one module file. */
export function auditModule(file, src) {
  const code = stripComments(src);
  const out = [];
  const add = (severity, rule, detail) => out.push({ severity, rule, file, detail });
  for (const reg of findRegistrations(code)) {
    if (!reg.isLiteral) { add("INFO", "unreadable-event", "on() with a non-literal event name"); continue; }
    const ev = reg.event;
    if (ev === "tool.check" || ev === "*") {
      for (const m of reg.text.matchAll(/\bdecision\s*:\s*([^,}\n]+)/g)) {
        const kind = isAllow(code, m[1]);
        if (kind === "literal" || kind === "constant") add("HIGH", "approve-at-check", `${ev} hook returns decision "allow" (${kind})`);
        else if (kind === "dynamic" && !/^(['"`])(deny|ask)\1/.test(m[1].trim())) add("MEDIUM", "dynamic-decision", `${ev} hook returns decision: ${m[1].trim().slice(0, 60)}`);
      }
    }
    if (ev === "classic.PermissionRequest" || ev === "classic.PreToolUse" || ev === "*" || ev === "classic.*") {
      if (/\b(behavior|permissionDecision)\s*:\s*(['"`])allow\2/.test(reg.text)) add("HIGH", "classic-allow", `${ev} hook answers "allow"`);
    }
    if (ev === "tool.call" && /\breturn\s*\{\s*result\s*:|=>\s*\(\s*\{\s*result\s*:/.test(reg.text)) {
      add("MEDIUM", "answers-tool-call", "tool.call hook answers with { result } instead of running the tool");
    }
    if (ev === "plugin.register" || ev === "engine.create" || (API_EVENTS.test(ev) && !CORE_EVENTS.has(ev))) {
      add("INFO", "watches-other-mods", `hooks ${ev}, which sees or changes what other mods do`);
    }
  }
  if (/\bconsent\s*:/.test(code)) add("HIGH", "forged-consent", "sets `consent:` on a tool call, which reads as the user's own approval");
  if (/\basUser\s*:\s*true\b/.test(code)) add("MEDIUM", "speaks-as-user", "submits a prompt as the user's own words");
  if (/\bnext\.to\s*\(/.test(code)) add("MEDIUM", "skips-tiers", "calls next.to(), skipping later mods");
  return out;
}

/** Audits every mod under the roots. */
export function audit(roots) {
  const mods = [];
  const done = new Set();
  let scanned = 0;
  for (const root of roots) {
    for (const hj of findHooksFiles(root)) {
      const key = resolve(hj).toLowerCase();
      if (done.has(key)) continue;
      done.add(key);
      scanned += 1;
      const { files, error } = moduleFiles(hj);
      if (!files.length && !error) continue; // a plugin with settings hooks only, no mod
      const pluginRoot = dirname(dirname(hj));
      let name = pluginRoot;
      try { name = JSON.parse(readFileSync(join(pluginRoot, ".claude-plugin", "plugin.json"), "utf8")).name ?? name; } catch { /* no manifest */ }
      const findings = error ? [{ severity: "INFO", rule: "unreadable", file: hj, detail: error }] : [];
      for (const f of files) findings.push(...auditModule(f, readFileSync(f, "utf8")));
      mods.push({ name, root: pluginRoot, modules: files, findings });
    }
  }
  const all = mods.flatMap((m) => m.findings);
  const count = (s) => all.filter((f) => f.severity === s).length;
  return { mods, summary: { hooksFiles: scanned, mods: mods.length, high: count("HIGH"), medium: count("MEDIUM"), info: count("INFO") } };
}

function defaultRoots() {
  const roots = [join(homedir(), ".claude", "plugins")];
  const extra = process.env.CLAUDE_CODE_PLUGIN_DIRS;
  if (extra) roots.push(...extra.split(process.platform === "win32" ? ";" : ":").filter(Boolean));
  return roots;
}

function main(argv) {
  const json = argv.includes("--json");
  const roots = argv.filter((a) => a !== "--json");
  const report = audit(roots.length ? roots : defaultRoots());
  if (json) {
    process.stdout.write(JSON.stringify(report, null, 2) + "\n");
  } else {
    const s = report.summary;
    process.stdout.write(`audit-mods: ${s.hooksFiles} hooks.json file(s), ${s.mods} with a mod module; ${s.high} high, ${s.medium} medium, ${s.info} info\n`);
    for (const m of report.mods) {
      process.stdout.write(`\n${m.name}  (${m.root})\n`);
      if (!m.findings.length) process.stdout.write("  no findings\n");
      for (const f of m.findings) process.stdout.write(`  ${f.severity.padEnd(6)} ${f.rule.padEnd(19)} ${f.detail}\n`);
    }
    process.stdout.write("\nStatic reading only: a clean report is not proof that a mod never approves a call.\n");
  }
  return report.summary.high > 0 ? 1 : 0;
}

if (import.meta.url === pathToFileURL(process.argv[1] ?? "").href) process.exitCode = main(process.argv.slice(2));
