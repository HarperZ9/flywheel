"""publish_lint.py — a pre-publish gate for shipped surfaces (zero-dep).

The scan-and-report MECHANISM is modeled on behavior-transform.io's
pressure_scan (declarative rules -> per-line findings -> severity + exit code),
copied and adapted here so the flywheel carries its own gate. It deliberately
does NOT import or reuse the WARDEN red-team vocabulary calibration: that corpus
false-positives on ordinary coding words and belongs to a private layer. This
brick's ruleset is product-appropriate — the things that must never reach a
public model page, README, or site:

  1. SECRETS      (error) — tokens/keys that must never be published.
  2. LOCAL_PATHS  (error) — build-machine paths (C:\\, E:\\, /mnt/…) leaking
                            into a shipped doc (the shipped-posture directive).
  3. DEV_REGISTER (warn)  — "Status: staged", "operator-gated", "TODO", and
                            other developer-doc language on a product surface.
  4. STALE_CLAIM  (warn)  — "no benchmark has been run", "pending", "coming
                            soon": claims that go stale the moment they ship.

Discipline shared with the rest of the harness: the verifier must be able to
FAIL. `--selftest` runs built-in fixtures — a dirty doc MUST raise one finding
of every category and a clean doc MUST raise none, or the linter is broken and
its verdicts cannot be trusted. Findings can be sealed into a re-checkable
receipt (`--receipt`).

Usage:
  python harness/publish_lint.py PATH ...           # scan, human output
  python harness/publish_lint.py --json PATH ...     # structured output
  python harness/publish_lint.py --strict PATH ...   # warnings also fail
  python harness/publish_lint.py --selftest          # falsifier self-check
  python harness/publish_lint.py --receipt R.json PATH ...

Exit codes: 0 clean · 1 error-severity findings (or warnings under --strict)
            · 2 usage/selftest failure.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Rule:
    rule_id: str
    category: str
    severity: str          # "error" | "warn"
    pattern: str
    message: str
    ignore_case: bool = False


# Product ruleset. Deliberately small and coding-product-appropriate — extend
# with real shipped-surface hazards, never with red-team vocabulary.
RULES: tuple[Rule, ...] = (
    # --- SECRETS (error) — obviously-fake canaries used only in --selftest ---
    Rule("secret.hf", "SECRETS", "error",
         r"\bhf_[A-Za-z0-9]{20,}\b", "Hugging Face token"),
    Rule("secret.openai", "SECRETS", "error",
         r"\bsk-[A-Za-z0-9]{20,}\b", "OpenAI-style secret key"),
    Rule("secret.aws", "SECRETS", "error",
         r"\bAKIA[0-9A-Z]{16}\b", "AWS access key id"),
    Rule("secret.github", "SECRETS", "error",
         r"\bgh[pousr]_[A-Za-z0-9]{20,}\b", "GitHub token"),
    Rule("secret.pem", "SECRETS", "error",
         r"-----BEGIN [A-Z ]*PRIVATE KEY-----", "private key block"),
    Rule("secret.assign", "SECRETS", "error",
         r"(?i)\b(api[_-]?key|secret|password|token)\b\s*[:=]\s*['\"][^'\"\s]{8,}['\"]",
         "inline credential assignment"),
    # --- LOCAL_PATHS (error) — build-machine paths in a shipped doc ----------
    # both slash forms: C:\dev and C:/dev are the same leaked machine path
    Rule("path.win", "LOCAL_PATHS", "error",
         r"[A-Za-z]:[\\/]+(?:Users|dev|tmp|local-model-run|Windows)",
         "Windows build-machine path"),
    Rule("path.wsl", "LOCAL_PATHS", "error",
         r"/mnt/[a-z]/(?:dev|Users|local-model-run)", "WSL build-machine path"),
    Rule("path.gitbash", "LOCAL_PATHS", "error",
         r"/c/(?:dev|Users)/", "Git-Bash build-machine path"),
    # --- DEV_REGISTER (warn) — developer-doc language on a product surface ---
    Rule("reg.status", "DEV_REGISTER", "warn",
         r"(?i)^\s*status:\s*(draft|staged|pending|wip|in progress)",
         "developer status line on a shipped surface"),
    Rule("reg.gated", "DEV_REGISTER", "warn",
         r"(?i)operator[- ](gated|approval|upload)", "operator-gate language"),
    Rule("reg.await", "DEV_REGISTER", "warn",
         r"(?i)awaiting (operator|upload|approval)", "await-gate language"),
    Rule("reg.todo", "DEV_REGISTER", "warn",
         r"\b(TODO|FIXME|XXX|HACK)\b", "in-progress marker"),
    Rule("reg.donotpub", "DEV_REGISTER", "warn",
         r"(?i)do[_ -]?not[_ -]?publish", "do-not-publish marker"),
    # --- UNANCHORED_CLAIM (warn) — tenet 4: no claim without its interval ----
    Rule("claim.nointerval", "UNANCHORED_CLAIM", "warn",
         r"(?i)^(?!.*(?:±|\+/-|\bCI\b|interval|\[))"
         r".*\b(?:pass@\d+|accuracy|score|win rate|success rate)\b"
         r"[^%\n]*\d+(?:\.\d+)?\s*%",
         "percentage metric with no interval"),
    Rule("claim.superlative", "UNANCHORED_CLAIM", "warn",
         r"(?i)\b(?:best(?!-of)|fastest|state[- ]of[- ]the[- ]art|"
         r"world[- ]class|leading)\b",
         "superlative without a measured comparison"),
    # --- STALE_CLAIM (warn) — claims that rot the moment they ship -----------
    Rule("stale.nobench", "STALE_CLAIM", "warn",
         r"(?i)no benchmark(s)? (has|have)? ?(been )?run", "stale 'no benchmark' claim"),
    Rule("stale.pending", "STALE_CLAIM", "warn",
         r"(?i)benchmark(s)? (are|is) pending", "stale 'benchmarks pending' claim"),
    Rule("stale.soon", "STALE_CLAIM", "warn",
         r"(?i)coming soon", "coming-soon claim"),
)

TEXT_SUFFIXES = {".md", ".markdown", ".txt", ".rst", ".html", ".json",
                 ".yaml", ".yml", ".toml", ".cfg", ".ini"}

_COMPILED = [(r, re.compile(r.pattern, re.IGNORECASE if r.ignore_case else 0))
             for r in RULES]


def scan_text(text: str, source: str = "<text>") -> list[dict]:
    findings: list[dict] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        for rule, rx in _COMPILED:
            m = rx.search(line)
            if m:
                findings.append({
                    "source": source, "line": lineno, "col": m.start() + 1,
                    "rule": rule.rule_id, "category": rule.category,
                    "severity": rule.severity, "message": rule.message,
                    "match": m.group(0)[:80],
                })
    return findings


def scan_path(path: Path) -> list[dict]:
    if path.suffix.lower() not in TEXT_SUFFIXES:
        return []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    return scan_text(text, source=str(path))


def _iter_files(paths: list[str]):
    for p in paths:
        pth = Path(p)
        if pth.is_dir():
            yield from (f for f in sorted(pth.rglob("*"))
                        if f.is_file() and ".git" not in f.parts)
        elif pth.is_file():
            yield pth


# ---- Selftest falsifier: the linter must be able to catch AND to pass -------
_DIRTY = (
    "Status: staged\n"
    "Download from C:\\Users\\you\\project and set token hf_ABCDEFGHIJKLMNOPQRSTUV.\n"
    "See X:/dev/example-repo for setup.\n"
    "No benchmark has been run yet.\n"
    "The best coding model: accuracy is 91% overall.\n"
)
_CLEAN = (
    "# Flywheel-Local-Coder-14B\n"
    "Run it in two commands. Pass@1 is 82.9% (95% CI 78.1-86.9) on the "
    "code-completion suite.\n"
)


def selftest() -> int:
    dirty = scan_text(_DIRTY, "<dirty-fixture>")
    cats = {f["category"] for f in dirty}
    required = {"SECRETS", "LOCAL_PATHS", "DEV_REGISTER", "STALE_CLAIM",
                "UNANCHORED_CLAIM"}
    clean = scan_text(_CLEAN, "<clean-fixture>")
    ok = required.issubset(cats) and not clean
    print(json.dumps({
        "selftest": "publish_lint",
        "dirty_categories": sorted(cats),
        "required": sorted(required),
        "dirty_ok": required.issubset(cats),
        "clean_findings": len(clean),
        "clean_ok": not clean,
        "verdict": "PASS" if ok else "FAIL",
    }, indent=1))
    if not ok:
        print("SELFTEST FALSIFIER FIRED: the linter cannot be trusted.")
        return 2
    return 0


def _receipt(findings: list[dict], files: list[str]) -> dict:
    payload = json.dumps({"files": sorted(files), "findings": findings},
                         sort_keys=True).encode()
    return {
        "schema": "flywheel.publish-lint-receipt/v1",
        "file_count": len(files),
        "finding_count": len(findings),
        "error_count": sum(1 for f in findings if f["severity"] == "error"),
        "warn_count": sum(1 for f in findings if f["severity"] == "warn"),
        "digest": hashlib.sha256(payload).hexdigest(),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="pre-publish gate for shipped surfaces")
    ap.add_argument("paths", nargs="*", help="files or directories to scan")
    ap.add_argument("--json", action="store_true", help="structured output")
    ap.add_argument("--strict", action="store_true", help="warnings also fail")
    ap.add_argument("--selftest", action="store_true", help="run the falsifier")
    ap.add_argument("--receipt", default="", help="write a re-checkable receipt JSON")
    a = ap.parse_args(argv)

    if a.selftest:
        return selftest()
    if not a.paths:
        ap.error("no paths given (use --selftest for the self-check)")

    files, findings = [], []
    for f in _iter_files(a.paths):
        files.append(str(f))
        findings.extend(scan_path(f))

    receipt = _receipt(findings, files)
    if a.receipt:
        Path(a.receipt).write_text(json.dumps(receipt, indent=1), encoding="utf-8")

    if a.json:
        print(json.dumps({"receipt": receipt, "findings": findings}, indent=1))
    else:
        for f in findings:
            print(f"  {f['severity'].upper():5s} {f['category']:12s} "
                  f"{f['source']}:{f['line']} [{f['rule']}] {f['message']}")
        print(f"scanned {len(files)} file(s): "
              f"{receipt['error_count']} error(s), {receipt['warn_count']} warning(s)")

    if receipt["error_count"] or (a.strict and receipt["warn_count"]):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
