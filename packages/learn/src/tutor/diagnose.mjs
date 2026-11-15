// Misconception diagnosis for arithmetic practice answers (docs/MISCONCEPTION-DIAGNOSIS.md).
//
// diagnose({prompt, answer}) walks a fixed tree of yes/no questions, one at a time, and returns
// the leaf it reaches plus the recorded path. Each question is answered by recomputing what a
// known procedure gives on the prompt's own numbers and comparing it to the operator's answer.
// INTEGRITY: the result names a cause; it never carries the correct answer or a worked solution.

const NO_ATTEMPT = new Set(["", "?", "??", "idk", "i dont know", "i don't know", "dont know",
  "don't know", "no idea", "n/a", "na", "-", "skip", "pass"]);
const FRACTION = /(\d+)\s*\/\s*(\d+)\s*\+\s*(\d+)\s*\/\s*(\d+)/;
const WHOLE = /(\d+)\s*([+\-x*×])\s*(\d+)/i;

export const LEAVES = Object.freeze({
  "missing.no_attempt": "missing", "missing.unexplained": "missing",
  "misrecruited.wrong_operation": "misrecruited", "misrecruited.smaller_from_larger": "misrecruited",
  "misrecruited.no_carry": "misrecruited", "misrecruited.fraction_add_across": "misrecruited",
  "slip.one_digit": "slip",
});

// parsePrompt("What is 507 - 248?") -> {kind:"whole", op:"-", a:507, b:248} | {kind:"fraction",...} | null
export function parsePrompt(prompt) {
  const text = String(prompt || "");
  const f = text.match(FRACTION);
  if (f) return { kind: "fraction", a: +f[1], b: +f[2], c: +f[3], d: +f[4] };
  const w = text.match(WHOLE);
  if (!w) return null;
  const op = w[2] === "x" || w[2] === "X" || w[2] === "×" ? "*" : w[2];
  return { kind: "whole", op, a: +w[1], b: +w[3] };
}

// parseAnswer("2/7") -> {kind:"fraction", n:2, d:7}; "1,204" -> {kind:"whole", v:1204}; else null
export function parseAnswer(answer) {
  const text = String(answer ?? "").trim().replace(/[,\s]/g, "");
  let m = text.match(/^(-?\d+)\/(\d+)$/);
  if (m) return { kind: "fraction", n: +m[1], d: +m[2] };
  m = text.match(/^-?\d+$/);
  return m ? { kind: "whole", v: +text } : null;
}

function digits(n) { return String(Math.abs(n)).split("").map(Number); }

function columnwise(a, b, fn, keepTop) {
  const da = digits(a).reverse(), db = digits(b).reverse();
  const width = Math.max(da.length, db.length);
  const out = [];
  for (let i = 0; i < width; i += 1) {
    const r = fn(da[i] || 0, db[i] || 0);
    out.push(keepTop && i === width - 1 ? r : r % 10);
  }
  return Number(out.reverse().join(""));
}

function sameValue(ans, n, d) {
  if (ans.kind === "fraction") return ans.d !== 0 && ans.n * d === n * ans.d;
  return d !== 0 && ans.v * d === n;
}

function oneDigitOff(got, want) {
  const g = String(got), w = String(want);
  if (g.length !== w.length || g === w) return false;
  const diff = [...g].map((ch, i) => (ch === w[i] ? -1 : i)).filter((i) => i >= 0);
  if (diff.length === 1) return true;
  return diff.length === 2 && diff[1] === diff[0] + 1 && g[diff[0]] === w[diff[1]] && g[diff[1]] === w[diff[0]];
}

function correctOf(p) {
  if (p.kind === "fraction") return { n: p.a * p.d + p.c * p.b, d: p.b * p.d };
  return { v: p.op === "+" ? p.a + p.b : p.op === "-" ? p.a - p.b : p.a * p.b };
}

function gcd(x, y) { return y ? gcd(y, x % y) : Math.abs(x); }

function wrongOperation(p, ans) {
  if (p.kind === "fraction") {
    return sameValue(ans, p.a * p.c, p.b * p.d) || sameValue(ans, p.a * p.d - p.c * p.b, p.b * p.d);
  }
  if (ans.kind !== "whole") return false;
  const all = { "+": p.a + p.b, "-": p.a - p.b, "*": p.a * p.b };
  const others = Object.entries(all).filter(([op]) => op !== p.op).map(([, v]) => v);
  if (p.op !== "-") others.push(p.b - p.a);
  return others.includes(ans.v);
}

function slip(p, ans) {
  const c = correctOf(p);
  if (p.kind === "whole") return ans.kind === "whole" && oneDigitOff(ans.v, c.v);
  if (ans.kind !== "fraction") return false;
  const g = gcd(c.n, c.d);
  return [[c.n, c.d], [c.n / g, c.d / g]].some(([n, d]) =>
    (ans.n === n && oneDigitOff(ans.d, d)) || (ans.d === d && oneDigitOff(ans.n, n)));
}

// The tree, in the order the questions are asked. Each test sees (prompt, answer) parsed.
const QUESTIONS = [
  ["Is the answer the fraction (a+c)/(b+d)?", "misrecruited.fraction_add_across",
    (p, a) => p.kind === "fraction" && a.kind === "fraction" && a.n === p.a + p.c && a.d === p.b + p.d],
  ["Does each column take the smaller digit from the larger?", "misrecruited.smaller_from_larger",
    (p, a) => p.kind === "whole" && p.op === "-" && a.kind === "whole" &&
      a.v === columnwise(p.a, p.b, (x, y) => Math.abs(x - y), false)],
  ["Does each column drop its carry?", "misrecruited.no_carry",
    (p, a) => p.kind === "whole" && p.op === "+" && a.kind === "whole" &&
      [false, true].some((top) => a.v === columnwise(p.a, p.b, (x, y) => x + y, top))],
  ["Is it what another operation gives on the same numbers?", "misrecruited.wrong_operation", wrongOperation],
  ["Is it one digit away from the right answer?", "slip.one_digit", slip],
];

function verdict(leaf, path, extra = {}) {
  return { leaf, top: leaf ? LEAVES[leaf] : null, path, ...extra };
}

// diagnose({prompt, answer}) -> {leaf, top, path:[{question, answer}]}; leaf is null when the
// prompt is not an arithmetic question this tree covers or the answer is in fact right.
export function diagnose({ prompt, answer }) {
  const blank = NO_ATTEMPT.has(String(answer ?? "").trim().toLowerCase());
  const path = [{ question: "Was no answer given?", answer: blank }];
  if (blank) return verdict("missing.no_attempt", path);
  const p = parsePrompt(prompt);
  const a = parseAnswer(answer);
  if (!p) return verdict(null, path, { reason: "prompt not covered" });
  if (!a) return verdict("missing.unexplained", path, { reason: "answer not a number" });
  const c = correctOf(p);
  if (p.kind === "fraction" ? sameValue(a, c.n, c.d) : a.kind === "whole" && a.v === c.v) {
    return verdict(null, path, { reason: "answer is correct" });
  }
  for (const [question, leaf, test] of QUESTIONS) {
    const hit = Boolean(test(p, a));
    path.push({ question, answer: hit });
    if (hit) return verdict(leaf, path);
  }
  return verdict("missing.unexplained", path);
}
