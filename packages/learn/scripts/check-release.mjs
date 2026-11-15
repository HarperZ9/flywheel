#!/usr/bin/env node
// Release gate, run by .github/workflows/release.yml before anything is packed.
//
//   node scripts/check-release.mjs <tag> [<owner/repo>] [--notes <file>]
//
// Passes when the tag is v<version> and every version site agrees with package.json:
// package-lock.json (both fields), src/index.mjs, the MCP serverInfo, and the newest CHANGELOG
// heading. With <owner/repo>, package.json's repository.url must name that repository, which
// npm checks when it records provenance. Each bin must start with #!/usr/bin/env node and a line
// feed. --notes writes the CHANGELOG section for the version, for the GitHub Release body.
// Exit 0 when every check passes; otherwise each problem prints on its own line and exit is 1.
import { readFileSync, writeFileSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const read = (rel) => readFileSync(join(ROOT, rel), "utf8");

function changelogSection(text, version) {
  const lines = text.split(/\r?\n/);
  // A heading may carry a date after the version: "## 2.2.0" or "## 2.2.0, 2026-10-03".
  const heading = new RegExp(`^## ${version.replace(/\./g, "\\.")}(?:[ ,(]|$)`);
  const start = lines.findIndex((l) => heading.test(l.trim()));
  if (start < 0) return null;
  let end = lines.findIndex((l, i) => i > start && l.startsWith("## "));
  if (end < 0) end = lines.length;
  return lines.slice(start + 1, end).join("\n").trim() + "\n";
}

export async function check(tag, repo) {
  const problems = [];
  const pkg = JSON.parse(read("package.json"));
  const v = pkg.version;
  if (tag !== `v${v}`) problems.push(`tag ${tag} does not match package.json version ${v} (expected v${v})`);
  const lock = JSON.parse(read("package-lock.json"));
  if (lock.version !== v) problems.push(`package-lock.json version is ${lock.version}`);
  if (lock.packages?.[""]?.version !== v) problems.push(`package-lock.json packages[""].version is ${lock.packages?.[""]?.version}`);
  const { version } = await import(pathToFileURL(join(ROOT, "src", "index.mjs")).href);
  if (version !== v) problems.push(`src/index.mjs version is ${version}`);
  const { handle } = await import(pathToFileURL(join(ROOT, "src", "mcp.mjs")).href);
  const init = await handle({ jsonrpc: "2.0", id: 1, method: "initialize", params: {} });
  if (init.result.serverInfo.version !== v) problems.push(`MCP serverInfo.version is ${init.result.serverInfo.version}`);
  const newest = read("CHANGELOG.md").match(/^## (\d+\.\d+\.\d+)\b/m);
  if (!newest || newest[1] !== v) problems.push(`the newest CHANGELOG heading is ${newest ? newest[1] : "missing"}`);
  if (repo) {
    const want = `git+https://github.com/${repo}.git`;
    if (pkg.repository?.url !== want) problems.push(`package.json repository.url is ${pkg.repository?.url}, expected ${want}`);
  }
  for (const [name, rel] of Object.entries(pkg.bin || {})) {
    if (!read(rel).startsWith("#!/usr/bin/env node\n")) problems.push(`bin ${name} (${rel}) does not start with #!/usr/bin/env node and a line feed`);
  }
  return { problems, version: v };
}

async function cli(argv) {
  const i = argv.indexOf("--notes");
  const notesFile = i >= 0 ? argv[i + 1] : null;
  const [tag, repo] = argv.filter((a, j) => i < 0 || (j !== i && j !== i + 1));
  if (!tag) {
    console.error("usage: node scripts/check-release.mjs <tag> [<owner/repo>] [--notes <file>]");
    return 2;
  }
  const { problems, version } = await check(tag, repo);
  if (notesFile) {
    const notes = changelogSection(read("CHANGELOG.md"), version);
    if (!notes) problems.push(`CHANGELOG.md has no section for ${version}`);
    else writeFileSync(notesFile, notes);
  }
  for (const p of problems) console.log(p);
  console.log(problems.length ? `release gate: ${tag} FAILED (${problems.length} problem(s))` : `release gate: ${tag} ok`);
  return problems.length ? 1 : 0;
}

process.exitCode = await cli(process.argv.slice(2));
