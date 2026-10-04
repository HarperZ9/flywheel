"""lean_ndjson.py -- read a lean4export file and fingerprint what it states.

lean4export (format 3.1.0) writes one JSON object per line: names, universe
levels and expressions, each with an integer id that later lines refer to,
then declarations. Every reference points to an earlier line, so one pass in
file order computes a content hash for every expression.

The hash is alpha-invariant: binder names and binder info are left out, and
`mdata` is transparent, matching the `Expr` equality the Lean bind program
uses. Constants enter the hash by name and universe levels, so the meaning
of a constant is compared separately, declaration by declaration
(`meaning_mismatches`), the way lean_bind_script.py walks it.

This module is pure Python and shares no code with Lean or with nanoda. It
reads the same export file the external kernel checks, so the statement the
second kernel accepted is the statement compared here.
"""
from __future__ import annotations

import hashlib
import json

FORMAT_MIN, FORMAT_MAX = (3, 1), (3, 2)
_DECL_KINDS = ("axiom", "def", "opaque", "thm", "quot", "inductive")


class ExportError(ValueError):
    """The text is not a lean4export file this module can read."""


def _h(*parts) -> str:
    body = json.dumps(parts, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


class Export:
    """Names, levels, expression hashes and declarations of one export."""

    def __init__(self, text: str):
        self.names = {0: ""}
        self.levels = {0: "0"}
        self.exprs: dict = {}
        self.consts: dict = {}       # expr id -> constant names used directly
        self.decls: dict = {}        # constant name -> (kind, record)
        self.meta: dict = {}
        lines = (text or "").splitlines()
        if not lines:
            raise ExportError("the export is empty")
        for n, line in enumerate(lines, 1):
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
            except ValueError as exc:
                raise ExportError(f"line {n} is not JSON ({exc})") from None
            if not isinstance(obj, dict):
                raise ExportError(f"line {n} is not a JSON object")
            try:
                self._take(obj)
            except (KeyError, TypeError, IndexError) as exc:
                raise ExportError(f"line {n} is malformed ({exc!r})") from None
        self._check_format()

    def _check_format(self):
        ver = str(self.meta.get("format", {}).get("version", ""))
        try:
            parts = tuple(int(p) for p in ver.split(".")[:2])
        except ValueError:
            parts = ()
        if len(parts) != 2 or not FORMAT_MIN <= parts < FORMAT_MAX:
            raise ExportError(f"export format {ver or 'missing'} is outside "
                              "the supported 3.1.x")

    # -- one line ---------------------------------------------------------
    def _take(self, o: dict):
        if "meta" in o:
            self.meta = o["meta"]
        elif "in" in o:
            if "str" in o:
                s = o["str"]
                comp = s["str"]
            else:
                s = o["num"]
                comp = f"#{int(s['i'])}"
            pre = self.names[s["pre"]]
            self.names[o["in"]] = f"{pre}.{comp}" if pre else comp
        elif "il" in o:
            self.levels[o["il"]] = self._level(o)
        elif "ie" in o:
            self._expr(o)
        else:
            kind = next((k for k in _DECL_KINDS if k in o), None)
            if kind is None:
                raise ExportError(f"unknown record {sorted(o)[:3]}")
            self._decl(kind, o[kind])

    def _level(self, o: dict) -> str:
        lv = self.levels
        if "succ" in o:
            return f"s({lv[o['succ']]})"
        if "max" in o:
            a, b = o["max"]
            return f"m({lv[a]},{lv[b]})"
        if "imax" in o:
            a, b = o["imax"]
            return f"im({lv[a]},{lv[b]})"
        return f"p({json.dumps(self.names[o['param']])})"

    def _expr(self, o: dict):
        e, x, c = o["ie"], self.exprs, self.consts
        used: frozenset = frozenset()
        if "bvar" in o:
            h = _h("bvar", int(o["bvar"]))
        elif "sort" in o:
            h = _h("sort", self.levels[o["sort"]])
        elif "const" in o:
            name = self.names[o["const"]["name"]]
            h = _h("const", name, [self.levels[u] for u in o["const"]["us"]])
            used = frozenset((name,))
        elif "app" in o:
            f, a = o["app"]["fn"], o["app"]["arg"]
            h, used = _h("app", x[f], x[a]), c[f] | c[a]
        elif "lam" in o or "forallE" in o:
            k = "lam" if "lam" in o else "forallE"
            b = o[k]
            h, used = _h(k, x[b["type"]], x[b["body"]]), \
                c[b["type"]] | c[b["body"]]
        elif "letE" in o:
            b = o["letE"]
            ids = (b["type"], b["value"], b["body"])
            h = _h("letE", *[x[i] for i in ids])
            used = c[ids[0]] | c[ids[1]] | c[ids[2]]
        elif "proj" in o:
            p = o["proj"]
            tn = self.names[p["typeName"]]
            h = _h("proj", tn, int(p["idx"]), x[p["struct"]])
            used = c[p["struct"]] | {tn}
        elif "natVal" in o:
            h = _h("nat", str(o["natVal"]))
        elif "strVal" in o:
            h = _h("str", o["strVal"])
        elif "mdata" in o:
            inner = o["mdata"]["expr"]
            h, used = x[inner], c[inner]
        else:
            raise ExportError(f"unknown expression {sorted(o)[:3]}")
        x[e], c[e] = h, used

    def _decl(self, kind: str, d: dict):
        if kind == "inductive":
            for t in d["types"]:
                self.decls[self.names[t["name"]]] = ("induct", t)
            for t in d["ctors"]:
                self.decls[self.names[t["name"]]] = ("ctor", t)
            for t in d["recs"]:
                self.decls[self.names[t["name"]]] = ("rec", t)
        else:
            self.decls[self.names[d["name"]]] = (kind, d)

    # -- queries ----------------------------------------------------------
    def _lps(self, d: dict) -> list:
        return [self.names[i] for i in d.get("levelParams", [])]

    def statement_sha256(self, name: str) -> str:
        """The alpha-invariant hash of a declaration's statement: its
        universe parameters and type. "" when the export lacks it."""
        if name not in self.decls:
            return ""
        _, d = self.decls[name]
        return _h("statement", self._lps(d), self.exprs[d["type"]])

    def decl_sha256(self, name: str) -> str:
        """What a declaration means: kind, universe parameters, type, and
        the value of a definition or opaque. A theorem's proof is left out,
        as in lean_bind_script.sameDecl."""
        kind, d = self.decls[name]
        x, nm = self.exprs, self.names
        base = [kind, self._lps(d), x[d["type"]]]
        if kind in ("def", "opaque"):
            base += [x[d["value"]], d.get("safety", d.get("isUnsafe"))]
        elif kind == "induct":
            base += [d[k] for k in ("numParams", "numIndices", "numNested",
                                    "isRec", "isUnsafe", "isReflexive")]
            base += [[nm[i] for i in d["all"]], [nm[i] for i in d["ctors"]]]
        elif kind == "ctor":
            base += [nm[d["induct"]]] + [d[k] for k in (
                "cidx", "numParams", "numFields", "isUnsafe")]
        elif kind == "rec":
            base += [d[k] for k in ("numParams", "numIndices", "numMotives",
                                    "numMinors", "k", "isUnsafe")]
            base += [[nm[i] for i in d["all"]],
                     [[nm[r["ctor"]], r["nfields"], x[r["rhs"]]]
                      for r in d["rules"]]]
        elif kind in ("axiom", "quot"):
            base += [d.get("isUnsafe"), d.get("kind")]
        return _h(*base)

    def meaning_deps(self, name: str) -> frozenset:
        kind, d = self.decls[name]
        c, nm = self.consts, self.names
        deps = set(c[d["type"]])
        if kind in ("def", "opaque"):
            deps |= c[d["value"]]
        elif kind == "induct":
            deps |= {nm[i] for i in d["ctors"]}
        elif kind == "rec":
            for r in d["rules"]:
                deps |= c[r["rhs"]]
        return frozenset(deps)


def meaning_mismatches(cand: Export, chal: Export, theorem: str) -> list:
    """Every constant the challenge statement reaches, followed through the
    challenge's own declarations, must be declared identically in the
    candidate's export. Returns the refusals, empty when all match."""
    if theorem not in chal.decls:
        return [f"the challenge export holds no {theorem}"]
    kind, d = chal.decls[theorem]
    todo, seen, out = list(chal.consts[d["type"]]), set(), []
    while todo:
        n = todo.pop()
        if n in seen:
            continue
        seen.add(n)
        if n not in chal.decls:
            out.append(f"the challenge export does not declare {n}")
        elif n not in cand.decls:
            out.append(f"the candidate export does not declare {n}")
        elif cand.decl_sha256(n) != chal.decl_sha256(n):
            out.append(f"{n} differs between the candidate and the challenge")
        else:
            todo.extend(chal.meaning_deps(n))
    return sorted(out)
