#!/usr/bin/env node
// provision.mjs - create the board's Cloudflare resources and write their ids
// into wrangler.toml.
//
// The deploy stalls on two account-specific ids that have to be read out of one
// command and pasted into two exact lines of a git-ignored file. A typo there
// fails at deploy time with an error that points at the binding rather than at
// the paste. This does the read and the write.
//
// It holds no credential of its own. Wrangler owns the session, and this script
// refuses to run rather than prompting for one, so nothing here can be tricked
// into collecting a key.

import { spawnSync } from 'node:child_process';
import { readFileSync, writeFileSync, existsSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const TOML = join(ROOT, 'wrangler.toml');
const EXAMPLE = join(ROOT, 'wrangler.toml.example');
const DB_NAME = 'bulletin';
const KV_BINDING = 'KEYS';
const FORCE = process.argv.includes('--force');

function wrangler(args, { quiet = true } = {}) {
  const r = spawnSync('npx', ['wrangler', ...args], {
    cwd: ROOT, encoding: 'utf8', shell: true,
    stdio: quiet ? 'pipe' : 'inherit',
  });
  return { code: r.status, out: (r.stdout || '') + (r.error ? String(r.error) : ''),
           err: r.stderr || '' };
}

/** Wrangler prints progress around its JSON, so take the first array. */
export function parseJsonArray(text) {
  const start = text.indexOf('[');
  if (start < 0) return null;
  const end = text.lastIndexOf(']');
  if (end <= start) return null;
  try {
    const v = JSON.parse(text.slice(start, end + 1));
    return Array.isArray(v) ? v : null;
  } catch {
    return null;
  }
}

function requireSession() {
  const { code, out, err } = wrangler(['whoami']);
  const text = out + err;
  // Deliberately not echoed: whoami prints the account it found.
  if (code !== 0 || /not logged in|auth token has expired/i.test(text)) {
    console.error('No Cloudflare session, so nothing can be created.\n');
    console.error('Run one of these yourself, then run this again:');
    console.error('  npx wrangler login          (opens a browser)');
    console.error('  set CLOUDFLARE_API_TOKEN    (a token with D1 + Workers KV edit)\n');
    console.error('This script will not ask you for a credential and cannot log in for you.');
    process.exit(1);
  }
  console.log('Cloudflare session found.');
}

function findD1() {
  const { out } = wrangler(['d1', 'list', '--json']);
  const rows = parseJsonArray(out) || [];
  const hit = rows.find((r) => r.name === DB_NAME);
  return hit ? hit.uuid || hit.database_id || hit.id : null;
}

function ensureD1() {
  const existing = findD1();
  if (existing) {
    console.log(`D1 "${DB_NAME}" already exists.`);
    return existing;
  }
  console.log(`Creating D1 "${DB_NAME}"...`);
  const { code, out, err } = wrangler(['d1', 'create', DB_NAME]);
  if (code !== 0) fail('d1 create', out + err);
  // Re-list rather than parse the create banner: the banner format has moved
  // between wrangler versions and the list is the same fact from the source.
  const id = findD1();
  if (!id) fail('d1 create', 'created, but the database is not in d1 list');
  return id;
}

function findKv() {
  const { out } = wrangler(['kv', 'namespace', 'list']);
  const rows = parseJsonArray(out) || [];
  // Wrangler titles a namespace <worker>-<binding>, but an operator who made it
  // by hand may have named it anything containing the binding.
  const exact = rows.find((r) => r.title === `${DB_NAME}-${KV_BINDING}`);
  const loose = rows.find((r) => String(r.title || '').includes(KV_BINDING));
  const hit = exact || loose;
  return hit ? hit.id : null;
}

function ensureKv() {
  const existing = findKv();
  if (existing) {
    console.log(`KV namespace for ${KV_BINDING} already exists.`);
    return existing;
  }
  console.log(`Creating KV namespace ${KV_BINDING}...`);
  const { code, out, err } = wrangler(['kv', 'namespace', 'create', KV_BINDING]);
  if (code !== 0) fail('kv namespace create', out + err);
  const id = findKv();
  if (!id) fail('kv namespace create', 'created, but it is not in the namespace list');
  return id;
}

function fail(what, detail) {
  console.error(`\n${what} failed.\n${detail.trim().slice(0, 1200)}`);
  process.exit(1);
}

/** Whether a config still carries the ids nobody filled in.
 *
 * The dead sentinels count as placeholders. They are shaped like real ids,
 * which is the point of them and also why a check for REPLACE_WITH alone would
 * read the unconfigured board as configured and refuse to write it. */
export function hasPlaceholderIds(text) {
  return /REPLACE_WITH|00000000-0000-4000-8000-000000000001|0{28}dead/.test(text);
}

/** A file already carrying real ids is not overwritten without --force. */
function guardExistingToml() {
  if (!existsSync(TOML) || FORCE) return;
  if (!hasPlaceholderIds(readFileSync(TOML, 'utf8'))) {
    console.error('wrangler.toml already holds ids that are not placeholders.');
    console.error('Re-run with --force if you mean to replace them.');
    process.exit(1);
  }
}

function writeToml(dbId, kvId) {
  const text = readFileSync(EXAMPLE, 'utf8')
    .replace('REPLACE_WITH_D1_DATABASE_ID', dbId)
    .replace('REPLACE_WITH_KV_NAMESPACE_ID', kvId);
  if (text.includes('REPLACE_WITH')) {
    fail('writing wrangler.toml', 'a placeholder survived the substitution');
  }
  writeFileSync(TOML, text, 'utf8');
  console.log('\nwrangler.toml written. It is git-ignored, as the ids belong to');
  console.log('one account and not to a public repository.');
}

function main() {
  requireSession();
  guardExistingToml();
  const dbId = ensureD1();
  const kvId = ensureKv();
  writeToml(dbId, kvId);
  console.log('\nNext, in order:');
  console.log('  npm run db:remote     apply the three schema files to the live D1');
  console.log('  npm run deploy        publish the Worker');
  console.log('  node scripts/smoke.mjs --base https://<the host deploy prints>');
}

// Importing this file for its helpers must not create anything.
if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main();
}
