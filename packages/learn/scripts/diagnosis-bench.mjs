#!/usr/bin/env node
// Score diagnose() against teacher labels: node scripts/diagnosis-bench.mjs LABELS.json
// The first 20 items by id are dev; the bar is scored on the rest. A seeded derangement of
// answers across prompts is the control (docs/MISCONCEPTION-DIAGNOSIS.md).
import { readFileSync } from "node:fs";
import { diagnose, LEAVES } from "../src/tutor/diagnose.mjs";

function rng(seed) {
  let s = seed >>> 0;
  return () => ((s = (Math.imul(s, 1664525) + 1013904223) >>> 0) / 2 ** 32);
}

export function derange(n, seed) {
  const r = rng(seed);
  for (;;) {
    const idx = [...Array(n).keys()];
    for (let i = n - 1; i > 0; i -= 1) {
      const j = Math.floor(r() * (i + 1));
      [idx[i], idx[j]] = [idx[j], idx[i]];
    }
    if (idx.every((v, i) => v !== i)) return idx;
  }
}

export function score(items) {
  const rows = items.map((it) => ({ it, d: diagnose({ prompt: it.prompt, answer: it.answer }) }));
  const leaf = rows.filter(({ it, d }) => d.leaf === it.label).length;
  const top = rows.filter(({ it, d }) => d.top === LEAVES[it.label]).length;
  const misses = rows.filter(({ it, d }) => d.leaf !== it.label)
    .map(({ it, d }) => ({ id: it.id, label: it.label, got: d.leaf }));
  return { n: items.length, leaf_agreement: leaf / items.length, top_agreement: top / items.length, misses };
}

export function run(items, seed = 20261003) {
  const sorted = [...items].sort((a, b) => a.id.localeCompare(b.id));
  const dev = sorted.slice(0, 20), test = sorted.slice(20);
  const perm = derange(test.length, seed);
  const shuffled = test.map((it, i) => ({ ...it, answer: test[perm[i]].answer }));
  const t = score(test), c = score(shuffled);
  return { dev: score(dev), test: t, control: { leaf_agreement: c.leaf_agreement },
    bar: { D1: t.leaf_agreement >= 0.8, D2: t.top_agreement >= 0.85, control: c.leaf_agreement < 0.5 } };
}

if (process.argv[1]?.endsWith("diagnosis-bench.mjs")) {
  const path = process.argv[2];
  if (!path) { console.error("usage: node scripts/diagnosis-bench.mjs LABELS.json"); process.exit(2); }
  console.log(JSON.stringify(run(JSON.parse(readFileSync(path, "utf8")).items), null, 2));
}
