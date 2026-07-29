"""fenced_extract.py -- recover a certificate body from a markdown-fenced
transport envelope, verbatim, and DECLARE that we did it.

THE DEFECT THIS ANSWERS. A pilot run of scripts/run_demo_pool.py against a
live qwen2.5:0.5b showed 0 of 8 candidates parsed as well-formed certificate
bodies. Every one of the 8 responses wrapped its JSON in a markdown code
fence (`` ```json ... ``` ``) despite the prompt template's explicit
instruction not to, and `harness.certificates.base.parse_certificate` refuses
anything before or after the JSON object on purpose ("trailing content after
the certificate object" -- see that module's docstring: refusing trailing
garbage is the cheapest smuggling channel there is). Stripping the fence by
hand and re-running the same unmodified checker showed the content
underneath was well-formed in 5 of 8 slots. The content is real; only the
transport envelope defeats the parser.

WHY EXTRACTING A FENCE IS LEGITIMATE AND NOT "FIXING THE ANSWER". A
certificate body is the JSON object `parse_certificate` parses. A markdown
fence around it is transport, not content, exactly the distinction
scripts/check_writing.py's `strip_code` already draws when it removes fenced
code from prose before scoring the prose: the fence marks a boundary between
two different channels, and reading the right side of that boundary for the
right consumer is not editing either side. This module only ever SLICES: it
finds the fenced span and returns it byte-for-byte. It never reformats,
completes, or otherwise repairs what is inside the fence. Malformed JSON
inside a fence comes out exactly as malformed as it went in, and
`parse_certificate` still refuses it -- that is the intended, tested
behavior, not a gap.

THE EXTRACTION POLICY IS DECLARED, NOT SILENT. `EXTRACTION` names it and
pins a version, scripts/run_demo_pool.py records that name in every run
manifest it writes, and a stranger reading a manifest can see exactly which
extraction rule (if any) sat between the model and the checker.

WHERE THIS RUNS, AND WHAT pool.py STILL STORES. harness/pool.py's `fill()`
consumes `proposer.generate(...).text` directly and content-addresses
whatever string that is; it is never modified by this change (see
scripts/run_demo_pool.py's own module docstring: "harness/pool.py is never
modified"). Since there is no post-generation hook inside `fill()` to attach
to, `ExtractingProposer` below sits BETWEEN the real proposer and `fill()`,
at the exact point run_demo_pool.py already constructs the proposer object.
Consequence, stated precisely because it matters: the text `fill()` digests
and writes under `<out_dir>/candidates/` is the EXTRACTED body, not the raw
model response -- pool.py's own on-disk cache holds the post-extraction
form. The raw, pre-extraction response is not silently dropped: pool.py's
slot schema (`{"slot", "seed", "temperature", "candidate_sha256", "error"}`)
has exactly one content field and no room to carry a second one without
editing harness/pool.py, which is out of bounds here. So `write_extraction_log`
below persists the raw text separately, content-addressed under
`<out_dir>/raw_candidates/`, and a sidecar `<out_dir>/extraction_log.json`
joins every filled slot to both its raw and extracted digests plus the fence
diagnostics, so a stranger can see what the model actually emitted and what
was handed to the checker, without either file having to pretend to be the
other.

stdlib only.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

EXTRACTION = "fenced-json-v1"

# A markdown fenced code block: three backticks, an optional language tag on
# the SAME line (e.g. "json"), a newline, the body, a newline, three
# backticks. Only the text between the two structural newlines is "the
# fence's content" in markdown's own sense -- the tag is discarded and
# nothing inside the body is touched. DOTALL so the body may itself contain
# newlines, and the body match is non-greedy so a second fence later in the
# text does not get swallowed into the first.
_FENCE_RE = re.compile(r"```[^\n]*\n(.*?)\n```", re.DOTALL)


@dataclass(frozen=True)
class Extraction:
    """What extract_fenced_body did to one raw response: the decision AND
    the evidence for it, so neither has to be re-derived later."""
    raw: str
    body: str
    fence_found: bool
    fence_count: int


def extract_fenced_body(text: str) -> Extraction:
    """Recover the JSON body from a markdown-fenced response, verbatim.

    No fence: `body` is `text` unchanged -- this is a passthrough, not a
    refusal, so an already-bare response is untouched.

    One or more fences: the FIRST fenced span is taken. This is a documented
    choice (see tests/test_fenced_extract.py), not an oversight -- a
    response is read top to bottom the way a human would, and a later fence
    is never preferred over an earlier one. `fence_count` still reports how
    many fenced spans were present, so a caller can see when the choice
    mattered.

    The extracted body is returned EXACTLY as sliced out, including if what
    is inside is itself malformed JSON. This function never parses,
    validates, reformats, or repairs the body; that is
    `harness.certificates.base.parse_certificate`'s job, and it runs
    downstream of this, unmodified.
    """
    if not isinstance(text, str):
        return Extraction(raw=text, body=text, fence_found=False,
                          fence_count=0)
    matches = list(_FENCE_RE.finditer(text))
    if not matches:
        return Extraction(raw=text, body=text, fence_found=False,
                          fence_count=0)
    first = matches[0]
    return Extraction(raw=text, body=first.group(1), fence_found=True,
                      fence_count=len(matches))


class _ExtractedResult:
    """Just enough to match what harness/pool.py's fill() reads: a `.text`
    attribute -- mirrors scripts/demo_proposer.py's GenerationResult."""
    __slots__ = ("text",)

    def __init__(self, text: str) -> None:
        self.text = text


class ExtractingProposer:
    """Wraps any proposer whose `.generate()` returns an object with
    `.text`. Applies `extract_fenced_body` to that text before
    harness/pool.py's `fill()` ever sees it, since `fill()` (never modified
    here) content-addresses whatever `.text` is, verbatim, with no
    extraction step of its own.

    Every call is appended to `.log`, in call order. `fill()` calls
    `proposer.generate()` once per (task, slot) in a fixed, single-threaded,
    task-major then slot-minor order, so `.log` lines up positionally with
    the filled pool's own successful slots in that same order -- see
    `write_extraction_log`, which performs exactly that join.
    """

    def __init__(self, inner) -> None:
        self._inner = inner
        self.log: list[Extraction] = []

    def generate(self, prompt: str, *, seed: int, temperature: float,
                 max_new_tokens: int) -> _ExtractedResult:
        # A raised exception here is a harness-attributed generation
        # failure under pool.fill's own contract (see demo_proposer.py's
        # docstring); it propagates unchanged and nothing is logged for
        # this call, since there is no raw text to record.
        result = self._inner.generate(
            prompt, seed=seed, temperature=temperature,
            max_new_tokens=max_new_tokens)
        # Mirrors the exact coercion harness/pool.py's fill() applies to
        # whatever .generate() returns, so extraction sees the same text
        # fill() would have digested had this wrapper not intercepted it.
        raw_text = result.text if isinstance(result.text, str) else str(result.text)
        extraction = extract_fenced_body(raw_text)
        self.log.append(extraction)
        return _ExtractedResult(extraction.body)


def write_extraction_log(out_dir, doc: dict, log: list) -> dict:
    """Sidecar record joining every filled slot to its raw and extracted
    forms, since pool.py's own slot schema (unmodified) has room for only
    one content field -- the extracted one, because that is what `fill()`
    received. Returns the doc it wrote, for a caller that wants a summary.

    Raw text is also persisted content-addressed under
    `<out_dir>/raw_candidates/`, a directory pool.py never writes to and
    never reads from, so this never collides with or edits the cache
    harness/pool.py owns.
    """
    from harness.pool import digest  # local import: harness read, not edited

    raw_dir = Path(out_dir) / "raw_candidates"
    raw_dir.mkdir(parents=True, exist_ok=True)
    calls = iter(log)
    records = []
    for entry in doc["entries"]:
        for slot in entry["slots"]:
            if slot["candidate_sha256"] is None:
                continue  # generation itself failed; nothing was extracted
            extraction = next(calls)
            raw_sha = digest(extraction.raw)
            raw_path = raw_dir / (raw_sha.split(":", 1)[1] + ".txt")
            if not raw_path.exists():                # content-addressed
                raw_path.write_text(extraction.raw, encoding="utf-8")
            records.append({
                "task_id": entry["task_id"], "slot": slot["slot"],
                "raw_sha256": raw_sha,
                "extracted_sha256": slot["candidate_sha256"],
                "fence_found": extraction.fence_found,
                "fence_count": extraction.fence_count,
            })
    log_doc = {"schema": "flywheel.demo-pool-extraction-log/v1",
              "policy": EXTRACTION, "records": records}
    Path(out_dir, "extraction_log.json").write_text(
        json.dumps(log_doc, indent=1, sort_keys=True), encoding="utf-8")
    return log_doc
