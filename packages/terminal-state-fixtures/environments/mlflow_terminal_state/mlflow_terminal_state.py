"""Terminal-state scoring environment.

An agent run's outcome is not pass-or-fail. It is one of a fixed set of terminal
states, and only some of them belong in a quality denominator. Collapsing them
the usual way (anything-not-pass counts as a fail) turns a provider outage or a
blocked launch into a fake regression. That noise is what this environment
measures a model's ability to remove.

The task: given one run record (five typed fields), classify it into the correct
terminal verdict and say whether it belongs in the quality denominator. Ground
truth comes from a deterministic reference scorer embedded below, enumerated
over every reachable field combination, so the dataset is exhaustive and every
answer is re-derivable on any machine.

Five fields, one axis each:

  execution   what the run did          returned | timeout | blocked | unlaunched
  provider    how the provider answered ok | rejected (structured) | malformed
  oracle      the independent check     pass | fail | absent
  receipt     integrity of the record   verified | mismatch | absent
  artifact    hashes recomputed         match | mismatch | absent
"""

from __future__ import annotations

import itertools
import json
import re
from dataclasses import dataclass
from enum import Enum

import verifiers as vf
from datasets import Dataset


# --- reference scorer (ground truth, deterministic) ---------------------------

class Verdict(str, Enum):
    VERIFIED = "verified"          # returned, oracle passed, receipt + artifacts intact
    REFUTED = "refuted"            # returned, but oracle failed or the record is inconsistent
    UNVERIFIABLE = "unverifiable"  # returned, but no oracle exists to check it
    REJECTED = "rejected"          # a structured provider refusal, not an attempt at the task
    MALFORMED = "malformed"        # output could not be parsed into a claim
    TIMEOUT = "timeout"            # ran out of time before a terminal answer
    NOT_LAUNCHED = "not_launched"  # blocked or never launched; not a run at all


@dataclass(frozen=True)
class RunRecord:
    execution: str            # returned | timeout | blocked | unlaunched
    provider: str = "ok"      # ok | rejected | malformed
    oracle: str = "absent"    # pass | fail | absent
    receipt: str = "absent"   # verified | mismatch | absent
    artifact: str = "absent"  # match | mismatch | absent


def score(run: RunRecord) -> tuple[Verdict, bool]:
    """Classify one run. Order matters: the states that must NOT count as
    failures are settled before oracle logic ever runs. Returns the verdict and
    whether the run counts in the quality denominator."""
    if run.execution in ("blocked", "unlaunched"):
        return Verdict.NOT_LAUNCHED, False
    if run.execution == "timeout":
        return Verdict.TIMEOUT, False
    if run.provider == "rejected":
        return Verdict.REJECTED, False
    if run.provider == "malformed":
        return Verdict.MALFORMED, False
    if run.receipt == "mismatch" or run.artifact == "mismatch":
        return Verdict.REFUTED, True
    if run.oracle == "absent":
        return Verdict.UNVERIFIABLE, False
    if run.oracle == "pass":
        return Verdict.VERIFIED, True
    return Verdict.REFUTED, True


# --- dataset: every reachable record, scored by the reference -----------------

FIELDS = {
    "execution": ["returned", "timeout", "blocked", "unlaunched"],
    "provider": ["ok", "rejected", "malformed"],
    "oracle": ["pass", "fail", "absent"],
    "receipt": ["verified", "mismatch", "absent"],
    "artifact": ["match", "mismatch", "absent"],
}

SYSTEM_PROMPT = """You are scoring agent-run records into terminal states.

A run record has five fields:
  execution: returned | timeout | blocked | unlaunched
  provider:  ok | rejected | malformed
  oracle:    pass | fail | absent
  receipt:   verified | mismatch | absent
  artifact:  match | mismatch | absent

Classification contract, applied in this exact order:
1. execution blocked or unlaunched -> verdict not_launched. Not a run at all;
   excluded from the quality denominator.
2. execution timeout -> verdict timeout. No terminal answer; excluded.
3. provider rejected -> verdict rejected. A structured provider refusal is not
   a task failure; excluded.
4. provider malformed -> verdict malformed. Output never parsed into a claim;
   excluded.
5. receipt mismatch or artifact mismatch -> verdict refuted. Integrity beats
   the oracle: a tampered record refutes the run even if the oracle passed.
   Counts in the denominator.
6. oracle absent -> verdict unverifiable. An honest null, not a pass; excluded.
7. oracle pass -> verdict verified. Counts in the denominator.
8. oracle fail -> verdict refuted. Counts in the denominator.

Only verified and refuted runs belong in the quality denominator. Answer with a
single JSON object and nothing else:
{"verdict": "<one of: verified, refuted, unverifiable, rejected, malformed, timeout, not_launched>", "in_denominator": true|false}"""


def build_dataset() -> Dataset:
    rows = []
    for combo in itertools.product(*FIELDS.values()):
        rec = RunRecord(**dict(zip(FIELDS.keys(), combo)))
        verdict, in_denom = score(rec)
        rows.append({
            "question": "Score this run record:\n" + json.dumps(rec.__dict__, indent=2),
            "answer": json.dumps({"verdict": verdict.value, "in_denominator": in_denom}),
        })
    return Dataset.from_list(rows)


# --- rewards ------------------------------------------------------------------

_JSON_RE = re.compile(r"\{[^{}]*\}")


def _last_json(text: str) -> dict | None:
    matches = _JSON_RE.findall(text or "")
    for raw in reversed(matches):
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and "verdict" in obj:
            return obj
    return None


def _completion_text(completion) -> str:
    if isinstance(completion, str):
        return completion
    # chat completions: list of messages; take the last assistant content
    try:
        return completion[-1]["content"] or ""
    except (TypeError, KeyError, IndexError):
        return str(completion)


def verdict_reward(completion, answer, **kwargs) -> float:
    """1.0 when the predicted verdict matches the reference scorer."""
    got = _last_json(_completion_text(completion))
    want = json.loads(answer)
    if got is None:
        return 0.0
    return 1.0 if got.get("verdict") == want["verdict"] else 0.0


def denominator_reward(completion, answer, **kwargs) -> float:
    """1.0 when the denominator membership matches. This is the claim the
    environment exists for: exclusions are as load-bearing as verdicts."""
    got = _last_json(_completion_text(completion))
    want = json.loads(answer)
    if got is None:
        return 0.0
    return 1.0 if got.get("in_denominator") == want["in_denominator"] else 0.0


# --- environment --------------------------------------------------------------

def load_environment(**kwargs) -> vf.Environment:
    rubric = vf.Rubric(
        funcs=[verdict_reward, denominator_reward],
        weights=[0.7, 0.3],
    )
    return vf.SingleTurnEnv(
        dataset=build_dataset(),
        system_prompt=SYSTEM_PROMPT,
        rubric=rubric,
        **kwargs,
    )
