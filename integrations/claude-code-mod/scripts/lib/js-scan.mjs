// Small static readers for hooks modules: strip comments, find on(...) calls
// and their hook bodies, and resolve a constant's string value.
//
// This is a lexer with heuristics, not a JavaScript parser. It reads what a
// mod's source says literally. Code that builds an event name or a decision
// at run time, or loads code another way, can hide from it; the audit reports
// those spots as "dynamic" where it can see them, and says so in its output.

/** Source with comments blanked to spaces (same length), strings kept. */
export function stripComments(src) {
  const out = src.split("");
  let i = 0;
  let lastSig = ""; // last significant code character, to tell regex from division
  const n = src.length;
  while (i < n) {
    const c = src[i];
    const d = src[i + 1];
    if (c === "/" && d === "/") {
      while (i < n && src[i] !== "\n") out[i++] = " ";
      continue;
    }
    if (c === "/" && d === "*") {
      out[i] = out[i + 1] = " ";
      i += 2;
      while (i < n && !(src[i] === "*" && src[i + 1] === "/")) { if (src[i] !== "\n") out[i] = " "; i += 1; }
      if (i < n) { out[i] = out[i + 1] = " "; i += 2; }
      continue;
    }
    if (c === '"' || c === "'" || c === "`") {
      i = skipString(src, i, c);
      lastSig = "a";
      continue;
    }
    if (c === "/" && (lastSig === "" || "(,=:[!&|?{};+-*%<>~^".includes(lastSig) || /\breturn\s*$/.test(src.slice(Math.max(0, i - 8), i)))) {
      const end = skipRegex(src, i);
      // Blank the pattern so brackets inside it cannot unbalance matchClose.
      for (let k = i + 1; k < end; k += 1) if (src[k] !== "\n" && !/[a-z/]/i.test(src[k])) out[k] = " ";
      i = end;
      lastSig = "a";
      continue;
    }
    if (!/\s/.test(c)) lastSig = c;
    i += 1;
  }
  return out.join("");
}

function skipString(src, i, q) {
  let j = i + 1;
  while (j < src.length) {
    if (src[j] === "\\") { j += 2; continue; }
    if (src[j] === q) return j + 1;
    if (q === "`" && src[j] === "$" && src[j + 1] === "{") {
      j = matchClose(src, j + 1, "{", "}") + 1;
      continue;
    }
    j += 1;
  }
  return j;
}

function skipRegex(src, i) {
  let j = i + 1;
  let inClass = false;
  while (j < src.length && src[j] !== "\n") {
    if (src[j] === "\\") { j += 2; continue; }
    if (src[j] === "[") inClass = true;
    else if (src[j] === "]") inClass = false;
    else if (src[j] === "/" && !inClass) { j += 1; break; }
    j += 1;
  }
  while (j < src.length && /[a-z]/i.test(src[j])) j += 1;
  return j;
}

/** Index of the bracket that closes the one at `open`, skipping strings. */
export function matchClose(src, open, o = "(", c = ")") {
  let depth = 0;
  for (let j = open; j < src.length; j += 1) {
    const ch = src[j];
    if (ch === '"' || ch === "'" || ch === "`") { j = skipString(src, j, ch) - 1; continue; }
    if (ch === o) depth += 1;
    else if (ch === c) { depth -= 1; if (depth === 0) return j; }
  }
  return src.length - 1;
}

/**
 * Every on(...) registration in comment-free code: { event, isLiteral, text,
 * start }. `text` is the whole call's source, which holds the hook body when
 * the hook is written inline. A hook passed by name has its function's body
 * appended when that function is declared in the same file.
 */
export function findRegistrations(code) {
  const regs = [];
  const re = /(^|[^\w$.])on\s*\(/g;
  const bare = blankStrings(code); // so "on (" inside a string is not a call
  let m;
  while ((m = re.exec(bare)) !== null) {
    const open = m.index + m[0].length - 1;
    const close = matchClose(code, open);
    const text = code.slice(open, close + 1);
    const lit = /^\(\s*(['"`])([^'"`]+)\1/.exec(text);
    const reg = { event: lit ? lit[2] : null, isLiteral: Boolean(lit), text, start: open };
    const named = /,\s*([A-Za-z_$][\w$]*)\s*\)\s*$/.exec(text);
    if (named) reg.text += "\n" + functionBody(code, named[1]);
    regs.push(reg);
  }
  return regs;
}

/** Code with every string literal's contents blanked (same length). */
export function blankStrings(code) {
  const out = code.split("");
  for (let i = 0; i < code.length; i += 1) {
    const c = code[i];
    if (c === '"' || c === "'" || c === "`") {
      const end = skipString(code, i, c);
      for (let k = i + 1; k < end - 1; k += 1) if (code[k] !== "\n") out[k] = " ";
      i = end - 1;
    }
  }
  return out.join("");
}

/** Source of `function name(...) {...}` or `const name = (...) => ...` in the file, or "". */
export function functionBody(code, name) {
  const decl = new RegExp(`function\\s*\\*?\\s*${escape(name)}\\s*\\(`).exec(code)
    ?? new RegExp(`(const|let|var)\\s+${escape(name)}\\s*=`).exec(code);
  if (!decl) return "";
  const brace = code.indexOf("{", decl.index);
  if (brace < 0) return "";
  return code.slice(decl.index, matchClose(code, brace, "{", "}") + 1);
}

/** The string a top-level `const NAME = 'value'` holds, or null. */
export function constString(code, name) {
  const m = new RegExp(`(const|let|var)\\s+${escape(name)}\\s*=\\s*(['"\`])([^'"\`]*)\\2`).exec(code);
  return m ? m[3] : null;
}

/** Relative import specifiers of a module ("./lib/x.mjs"). */
export function relativeImports(code) {
  const out = [];
  const re = /\bimport\s+(?:[^'"`;]*?\s+from\s+)?(['"])(\.{1,2}\/[^'"]+)\1/g;
  let m;
  while ((m = re.exec(code)) !== null) out.push(m[2]);
  return out;
}

function escape(s) {
  return s.replace(/[$]/g, "\\$");
}
