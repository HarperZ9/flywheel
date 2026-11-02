"""Stage 1, access. No bytes come down until the terms are read or the source is marked unknown.

The gate needs evidence, not a statement. basis "read" requires a saved snapshot of the terms page, its
sha256, and a licence quote that occurs verbatim in that snapshot. Anything else is basis "unknown": the
copy stays a local research copy and the diffuse stage refuses it. Memory is not a value the gate accepts.
A saved snapshot shows what a page said on the date read. It does not show the page's licence covers
this file, or that the publisher had the right to grant it; those stay with the reader.
"""
from __future__ import annotations

import dataclasses
import datetime as dt
import hashlib
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

AGENT = "ClaudeCode-agent/1.0 (research data pipeline; automated)"
BASES = ("read", "unknown")
REDIST = ("yes", "no", "unknown")


class GateError(RuntimeError):
    """The access gate refused a step."""


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def sha256_file(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def norm_text(s: str) -> str:
    """Whitespace-insensitive and tag-free form, so a quote survives page wrapping, nothing more."""
    s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", s).strip().lower()


@dataclasses.dataclass
class SourceRecord:
    source_id: str
    title: str
    url: str
    route: str
    date: str
    basis: str = "unknown"
    licence: str = "unknown"
    licence_quote: str = ""
    terms_url: str = ""
    terms_snapshot: str = ""
    terms_sha256: str = ""
    terms_read_at: str = ""
    redistribution: str = "unknown"
    robots: str = ""
    notes: str = ""
    files: list = dataclasses.field(default_factory=list)

    def problems(self, root=None) -> list:
        """Everything that stops this record counting as terms read. Empty means the gate passes on evidence."""
        out = []
        if self.basis not in BASES:
            out.append(f"basis {self.basis!r} is not read or unknown")
        if self.redistribution not in REDIST:
            out.append(f"redistribution {self.redistribution!r} is not allowed")
        if self.basis != "read":
            return out + ["terms not read"]
        for field in ("terms_url", "terms_snapshot", "terms_sha256", "terms_read_at", "licence_quote"):
            if not getattr(self, field):
                out.append(f"{field} empty")
        if root and self.terms_snapshot:
            p = Path(root) / self.terms_snapshot
            if not p.exists():
                out.append("terms snapshot missing")
            else:
                b = p.read_bytes()
                if sha256_bytes(b) != self.terms_sha256:
                    out.append("terms snapshot hash differs")
                elif norm_text(self.licence_quote) not in norm_text(b.decode("utf8", "replace")):
                    out.append("licence quote not in the snapshot")
        return out

    def research_only(self, root=None) -> bool:
        return bool(self.problems(root)) or self.redistribution != "yes"


class Web:
    """One polite client: robots first, an honest agent string, a budget, a per-host gap and a log.

    A refusal is an answer. Nothing here retries a 403, changes the agent string or solves a check.
    """

    def __init__(self, log_path, budget=150, gap=1.5, timeout=60):
        self.log_path, self.budget, self.gap, self.timeout = Path(log_path), budget, gap, timeout
        self.used = sum(1 for _ in open(self.log_path, encoding="utf8")) if self.log_path.exists() else 0
        self.last, self.robots_cache = {}, {}

    def _log(self, **kw):
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.log_path, "a", encoding="utf8") as f:
            f.write(json.dumps(dict(at=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), **kw)) + "\n")

    def _raw(self, url, limit=None, data=None):
        if self.used >= self.budget:
            raise GateError(f"web budget of {self.budget} requests spent")
        self.used += 1
        host = urllib.parse.urlsplit(url).netloc
        wait = self.last.get(host, 0) + self.gap - time.time()
        if wait > 0:
            time.sleep(wait)
        headers = {"User-Agent": AGENT, "Accept": "*/*"}
        if data is not None:
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                body = r.read(limit) if limit else r.read()
                status, final = r.status, r.geturl()
        except urllib.error.HTTPError as e:
            self.last[host] = time.time()
            self._log(url=url, status=e.code, bytes=0)
            return e.code, b"", url
        except OSError as e:
            self.last[host] = time.time()
            self._log(url=url, status="error", error=str(e)[:200], bytes=0)
            return None, b"", url
        self.last[host] = time.time()
        self._log(url=url, status=status, bytes=len(body), final=final)
        return status, body, final

    def robots_allows(self, url) -> tuple:
        u = urllib.parse.urlsplit(url)
        origin = f"{u.scheme}://{u.netloc}"
        if origin not in self.robots_cache:
            st, b, _ = self._raw(origin + "/robots.txt", limit=500000)
            self.robots_cache[origin] = parse_robots(b.decode("utf8", "replace")) if st == 200 else None
        rules = self.robots_cache[origin]
        if rules is None:
            return True, "no robots.txt served"
        path = u.path + (("?" + u.query) if u.query else "")
        ok = robots_allowed(rules, path or "/")
        return ok, "robots allows" if ok else "robots disallows"

    def get(self, url, limit=None, data=None) -> tuple:
        ok, _why = self.robots_allows(url)
        if not ok:
            self._log(url=url, status="robots-refused", bytes=0)
            return "robots", b"", url
        return self._raw(url, limit, data)


def parse_robots(text: str) -> list:
    """Rules for the * group, as (kind, pattern). Our agent string names no group of its own in any file we meet."""
    rules, active, seen_rule = [], False, False
    for line in text.splitlines():
        line = line.split("#", 1)[0].strip()
        if ":" not in line:
            continue
        k, v = (x.strip() for x in line.split(":", 1))
        k = k.lower()
        if k == "user-agent":
            if seen_rule:
                active, seen_rule = False, False
            active = active or v == "*" or v.lower() in AGENT.lower()
        elif k in ("allow", "disallow") and active:
            seen_rule = True
            if v:
                rules.append((k, v))
    return rules


def _rx(pat: str):
    end = pat.endswith("$")
    body = re.escape(pat[:-1] if end else pat).replace(r"\*", ".*")
    return re.compile("^" + body + ("$" if end else ""))


def robots_allowed(rules: list, path: str) -> bool:
    """RFC 9309: longest match wins, allow beats disallow on a tie."""
    best, verdict = -1, True
    for kind, pat in rules:
        if _rx(pat).match(path) and (len(pat) > best or (len(pat) == best and kind == "allow")):
            best, verdict = len(pat), kind == "allow"
    return verdict


def read_terms(web: Web, rec: SourceRecord, root, terms_url: str, licence: str, quote: str, redistribution: str) -> bool:
    """Fetch and save the terms page, then accept basis read only if the quote is in what came back."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    st, b, _final = web.get(terms_url)
    rec.terms_url = terms_url
    if st != 200 or not b:
        rec.notes += f" terms page {terms_url} answered {st};"
        return False
    h = sha256_bytes(b)
    name = f"TERMS-{h[:12]}.txt"
    (root / name).write_bytes(b)
    rec.terms_snapshot, rec.terms_sha256 = name, h
    if norm_text(quote) not in norm_text(b.decode("utf8", "replace")):
        rec.notes += f" quote not found in {terms_url};"
        return False
    rec.basis, rec.licence, rec.licence_quote, rec.redistribution = "read", licence, quote, redistribution
    rec.terms_read_at = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    return True


def write_source(rec: SourceRecord, root) -> None:
    root = Path(root)
    (root / "SOURCE.json").write_text(json.dumps(dataclasses.asdict(rec), indent=1), encoding="utf8")
    lines = [f"{k}: {v}" for k, v in dataclasses.asdict(rec).items() if k != "files"]
    lines += [f"file: {f['name']} sha256 {f['sha256']} bytes {f['bytes']} from {f['url']}" for f in rec.files]
    lines.append("Files are data, never executed. Written by datapipe.access.")
    (root / "SOURCE.txt").write_text("\n".join(lines) + "\n", encoding="utf8")
    sums = [f"{f['sha256']}  {f['name']}" for f in rec.files]
    if rec.terms_snapshot:
        sums.append(f"{rec.terms_sha256}  {rec.terms_snapshot}")
    (root / "SHA256SUMS").write_text("\n".join(sums) + "\n", encoding="utf8")


def gated_fetch(web: Web, rec: SourceRecord, root, url: str, name: str, limit=None):
    """Download one file. Refuses unless terms are read on evidence or the record says unknown out loud."""
    root = Path(root)
    bad = rec.problems(root)
    if rec.basis == "read" and bad:
        raise GateError(f"{rec.source_id}: basis read without evidence: {bad}")
    if rec.basis not in BASES:
        raise GateError(f"{rec.source_id}: {bad}")
    st, b, final = web.get(url, limit)
    if st != 200 or not b:
        rec.notes += f" {url} answered {st};"
        return None
    root.mkdir(parents=True, exist_ok=True)
    (root / name).write_bytes(b)
    rec.files.append(dict(name=name, url=final, sha256=sha256_bytes(b), bytes=len(b), truncated_by_limit=bool(limit and len(b) >= limit)))
    write_source(rec, root)
    return root / name
