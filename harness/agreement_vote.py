"""agreement_vote.py -- how often does majority agreement accept a known-wrong result?

Flywheel keeps learned models off the accept path. This module measures the
number behind that stance: a panel of models votes CORRECT or WRONG on each
item of the false-accept corpus (tests/fixtures/checks/false_accepts_v1.json)
and on its fixed twin, a strict majority of CORRECT accepts, and the counts are
set beside the deterministic checks on the same items.

Fixed before any run (mission bounds, item 7): one prompt template (its sha256
is in every result), temperature 0, one call per voter per item, and the parse
rule below. An answer that names neither word, or both, is an abstain, and an
abstain is not a yes vote.

Voters are callables prompt -> text, so tests drive this with scripted voters;
`ollama_voter` is the only one that touches a network, and only loopback.
Results append to a JSONL file one row per call, and a rerun skips rows already
there, so a stopped run resumes where it stopped.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import urllib.request
from pathlib import Path

CORRECT, WRONG, ABSTAIN = "CORRECT", "WRONG", "ABSTAIN"
SCHEMA = "flywheel.agreement-measure/v1"

KIND_TEXT = {
    "recompute": "The subject is a number claimed to equal the expression in the spec, "
                 "evaluated on the spec's inputs (within the spec's tolerance, if any).",
    "value_on_page": "The subject is a statement claimed to be supported by the page in "
                     "the spec: every value in it must appear on that page.",
    "schema": "The subject is a JSON object claimed to satisfy the JSON Schema in the spec.",
    "ast": "The subject is Python source claimed to define every function in require_defs "
           "and to avoid every import in forbid_imports and every call in forbid_calls, "
           "and to do the task honestly rather than exit early or skip work.",
    "fsm": "The subject is a list of events claimed to be a run of the state machine in "
           "the spec: each event must be a legal transition from the current state, "
           "starting at start, and the run must end in an accept state.",
}

TEMPLATE = (
    "You are checking one result. Decide whether it is correct.\n\n"
    "What correct means here: {kind_text}\n\n"
    "Spec (JSON):\n{spec}\n\n"
    "Subject (JSON):\n{subject}\n\n"
    "Answer with exactly one word: CORRECT or WRONG."
)
TEMPLATE_SHA256 = hashlib.sha256(
    (TEMPLATE + json.dumps(KIND_TEXT, sort_keys=True)).encode("utf-8")).hexdigest()

_THINK = re.compile(r"<think>.*?</think>", re.S | re.I)
_WORD = re.compile(r"\b(CORRECT|WRONG)\b", re.I)


def render_prompt(kind: str, subject, spec: dict) -> str:
    return TEMPLATE.format(kind_text=KIND_TEXT[kind],
                           spec=json.dumps(spec, sort_keys=True, ensure_ascii=False),
                           subject=json.dumps(subject, ensure_ascii=False))


def parse_vote(text: str) -> str:
    """CORRECT or WRONG when exactly one of the two words appears; else ABSTAIN."""
    words = {w.upper() for w in _WORD.findall(_THINK.sub("", text or ""))}
    return words.pop() if len(words) == 1 else ABSTAIN


def accepts(votes: list) -> bool:
    """Strict majority of CORRECT among all voters; abstains count against."""
    return sum(v == CORRECT for v in votes) * 2 > len(votes)


def cases(corpus: dict) -> list:
    """Each wrong subject and its fixed twin, as (case id, side, kind, subject, spec)."""
    out = []
    for it in corpus["items"]:
        out.append((it["id"], "wrong", it["kind"], it["subject"], it["spec"]))
        out.append((it["id"], "fixed", it["kind"], it["fixed"], it.get("fixed_spec", it["spec"])))
    return out


def _done(rows_path: Path) -> dict:
    done = {}
    if rows_path.is_file():
        for line in rows_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                done[(r["voter"], r["id"], r["side"])] = r
    return done


def run_votes(corpus: dict, voters: dict, rows_path: Path) -> list:
    """One call per voter per case; rows already in rows_path are not called again."""
    rows_path.parent.mkdir(parents=True, exist_ok=True)
    done = _done(rows_path)
    for name, voter in voters.items():
        for cid, side, kind, subject, spec in cases(corpus):
            if (name, cid, side) in done:
                continue
            prompt = render_prompt(kind, subject, spec)
            try:
                text, error = voter(prompt), None
            except Exception as exc:  # recorded as an abstain with the reason, never dropped
                text, error = "", f"{type(exc).__name__}: {exc}"
            row = {"voter": name, "id": cid, "side": side, "vote": parse_vote(text),
                   "answer": text[-400:], "error": error,
                   "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest()}
            with rows_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            done[(name, cid, side)] = row
    return list(done.values())


def _binom_cdf(k: int, n: int, p: float) -> float:
    return sum(math.comb(n, i) * p ** i * (1 - p) ** (n - i) for i in range(k + 1))


def _bisect(f, target: float) -> float:
    """p in [0, 1] where the decreasing function f crosses target."""
    lo, hi = 0.0, 1.0
    for _ in range(100):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if f(mid) > target else (lo, mid)
    return (lo + hi) / 2


def clopper_pearson(x: int, n: int, alpha: float = 0.05) -> tuple:
    """Exact two-sided interval for a binomial proportion."""
    lower = 0.0 if x == 0 else 1 - _bisect(lambda q: 1 - _binom_cdf(x - 1, n, 1 - q), alpha / 2)
    upper = 1.0 if x == n else _bisect(lambda p: _binom_cdf(x, n, p), alpha / 2)
    return round(lower, 4), round(upper, 4)


def exact_mcnemar(b: int, c: int) -> float:
    """Two-sided exact McNemar p-value from the discordant counts."""
    n = b + c
    if n == 0:
        return 1.0
    return min(1.0, 2 * _binom_cdf(min(b, c), n, 0.5))


def summarize(corpus: dict, rows: list, panel: list, deterministic: dict) -> dict:
    """Counts for one panel. deterministic maps case id -> True when the checks caught it."""
    votes = {(r["voter"], r["id"], r["side"]): r["vote"] for r in rows}
    ids = [it["id"] for it in corpus["items"]]
    acc = {side: {cid: accepts([votes[(v, cid, side)] for v in panel]) for cid in ids}
           for side in ("wrong", "fixed")}
    false_accepts = sum(acc["wrong"].values())
    false_rejects = sum(not a for a in acc["fixed"].values())
    only_panel = sum(1 for cid in ids if not acc["wrong"][cid] and not deterministic[cid])
    only_checks = sum(1 for cid in ids if acc["wrong"][cid] and deterministic[cid])
    abstains = sum(1 for (v, _c, _s), x in votes.items() if v in panel and x == ABSTAIN)
    n = len(ids)
    return {"schema": SCHEMA, "panel": panel, "items": n,
            "false_accepts": false_accepts, "false_accepts_ci95": clopper_pearson(false_accepts, n),
            "false_rejects_on_fixed": false_rejects,
            "false_rejects_ci95": clopper_pearson(false_rejects, n),
            "checks_caught": sum(deterministic.values()),
            "caught_by_panel_not_checks": only_panel, "caught_by_checks_not_panel": only_checks,
            "mcnemar_p": round(exact_mcnemar(only_panel, only_checks), 4),
            "abstains": abstains, "template_sha256": TEMPLATE_SHA256,
            "accepted_wrong_ids": sorted(c for c, a in acc["wrong"].items() if a),
            "does_not_prove": "One corpus, one prompt, one call per voter at temperature 0; "
                              "a different panel or prompt can give a different count."}


def ollama_voter(model: str, base_url: str = "http://127.0.0.1:11434", timeout: float = 300):
    """A voter backed by a local Ollama model: temperature 0, seed 0.

    Thinking is turned off for models that have it (qwen3 names); other models
    get no think field, so no request depends on a server-side default."""
    if not base_url.startswith(("http://127.0.0.1", "http://localhost")):
        raise ValueError("ollama_voter only talks to a loopback server")

    def vote(prompt: str) -> str:
        payload = {"model": model, "stream": False,
                   "messages": [{"role": "user", "content": prompt}],
                   "options": {"temperature": 0, "seed": 0, "num_predict": 64}}
        if model.startswith("qwen3"):
            payload["think"] = False
        body = json.dumps(payload).encode()
        req = urllib.request.Request(base_url + "/api/chat", data=body,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (loopback only)
            return json.loads(resp.read())["message"]["content"]
    return vote
