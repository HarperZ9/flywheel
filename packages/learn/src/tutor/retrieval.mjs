// Retrieval-practice module — turns the operator's OWN assist-extracted claims into cloze/recall
// prompts, and provides a deterministic interleaved study order.
//
// INTEGRITY: clozePrompts blanks a salient term out of a claim the OPERATOR already wrote (via
// assist()). It never adds an "answer"/"solution" field — the blanked term is withheld, not
// revealed, so the operator must retrieve it from memory. The prompt only carries a `source`
// (a cited URL, or the assist result's own content hash) so the operator can go check their own
// work after attempting recall; it is a study aid, never a graded answer key.
//
// interleave() mixes objectives across a study session deterministically (seed-based). No
// Math.random anywhere — same seed always reproduces the same order, so tests stay deterministic.

const NUMBER_RE = /\b\d[\d.,]*%?\b/;
const CAP_WORD_RE = /\b[A-Z][A-Za-z]{2,}\b/;

// Pick the salient span to blank out of a single claim's text, preferring (in order):
//   1. a number/percentage (the most checkable, most "fact-like" token)
//   2. a capitalized word/term that is not the first word of the sentence (a named concept)
//   3. the longest word in the sentence (fallback so every claim can still produce a prompt)
function pickBlank(text) {
  const numMatch = NUMBER_RE.exec(text);
  if (numMatch) return numMatch[0];

  // Scan for capitalized words after position 0 (skip the sentence-initial capital).
  const capRe = new RegExp(CAP_WORD_RE.source, "g");
  let m;
  let best = null;
  while ((m = capRe.exec(text))) {
    if (m.index > 0) { best = m[0]; break; }
  }
  if (best) return best;

  const words = text.split(/\s+/).filter(Boolean).map((w) => w.replace(/^[^\w]+|[^\w]+$/g, ""));
  const longest = words.filter(Boolean).sort((a, b) => b.length - a.length)[0];
  return longest || null;
}

function blank(text, term) {
  if (!term) return null;
  const idx = text.indexOf(term);
  if (idx === -1) return null;
  return text.slice(0, idx) + "___" + text.slice(idx + term.length);
}

// clozePrompts(assistResult, {objective}?) -> [{objective, prompt, source}]
export function clozePrompts(assistResult, { objective = null } = {}) {
  const claims = assistResult.claims || [];
  const sources = assistResult.sources || [];
  const fallbackSource = assistResult.inputSha256 ? `sha256:${assistResult.inputSha256}` : "";

  const out = [];
  for (const claim of claims) {
    const term = pickBlank(claim.text);
    const prompt = blank(claim.text, term);
    if (!prompt) continue; // could not form a blank; skip rather than emit a broken prompt
    out.push({
      objective,
      prompt,
      source: sources[0] || fallbackSource,
    });
  }
  return out;
}

// --- deterministic seeded shuffle (mulberry32) ---------------------------------------------
function mulberry32(seed) {
  let a = seed >>> 0;
  return function () {
    a |= 0; a = (a + 0x6D2B79F5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function seedToInt(seed) {
  if (typeof seed === "number") return seed >>> 0;
  const s = String(seed ?? "learn-interleave");
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

// interleave(objectives, {seed}) -> deterministically shuffled order (Fisher-Yates, seeded PRNG).
// No Math.random: the same seed always reproduces the same permutation.
export function interleave(objectives, { seed = "learn-interleave" } = {}) {
  const arr = [...objectives];
  const rand = mulberry32(seedToInt(seed));
  for (let i = arr.length - 1; i > 0; i--) {
    const j = Math.floor(rand() * (i + 1));
    [arr[i], arr[j]] = [arr[j], arr[i]];
  }
  return arr;
}
