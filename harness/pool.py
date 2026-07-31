"""pool.py -- cache the candidates once, then every arm is offline and paired.

The defect this replaces. `uplift_bench.py` ran a baseline arm at one attempt and
a treatment arm at several, generating fresh each time and stopping on the first
accept. The treatment's first attempt is the identical seed-0 temperature-0 call
as the baseline's only attempt, so one arm CONTAINS the other: the difference
cannot be negative, and across all thirteen runs ever made there is not a single
task the baseline passed and the treatment failed. A two-sided interval on that
difference tests a null that construction excluded.

The shape here is not ours. `verifiers` ships it as its `best-of-n` environment:
n independent attempts per episode, metrics marking the argmax sibling and
whether any reached threshold. We were the deviation from a known-good shape, so
this matches it rather than inventing a third.

Four properties, and each one buys something specific:

  1. **No early stopping.** Exactly K candidates per task, always, even after one
     is accepted. Stopping early is what made the arms nested, and it is also
     what made replicates look expensive: the discarded candidates were the ones
     a second arm needed.
  2. **Generation is decoupled from selection.** Filling the pool costs GPU once.
     Every arm after that is a pure function of the cache, so a stranger
     recomputes the entire analysis on a laptop with no GPU and no network, and
     adding an arm costs no generation at all.
  3. **Exact pairing.** All arms see the identical candidate set per task, so
     McNemar on discordant pairs is applicable, which it is not when two arms
     generate separately.
  4. **Content addressing.** A candidate is stored under the digest of its own
     bytes, so the same text from two runs is one object, and a candidate cannot
     be edited without changing where it lives.

What a pool deliberately does NOT decide: whether an accept is correct. The pool
holds candidates and fingerprints. Acceptors live in `pool_arms.py` and the
verdict authority stays the oracle.

One honest limit, stated here because it is easy to forget: a pool pins the
generation, not the model. If the serving stack is nondeterministic at
temperature 0, two pools built from one fingerprint will differ, and the pool
records enough to SEE that (per-slot digests) without being able to prevent it.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

SCHEMA = "flywheel.candidate-pool/v1"
INDEX_NAME = "pool_index.json"

# Every field a rerun needs to be the same experiment. Absent values are recorded
# as None rather than omitted, so a missing pin is visible instead of implied.
FINGERPRINT_FIELDS = (
    "model_ref", "model_digest", "engine", "engine_version", "quantization",
    "k", "seeds", "temperatures", "max_new_tokens", "prompt_template_sha256",
)


class PoolError(ValueError):
    """A pool that would report more than it holds."""


def digest(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def canonical(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), allow_nan=False)


def make_fingerprint(**kw) -> dict:
    """The pinned identity of a generation run. Unknown keys are refused: a
    fingerprint that silently accepts a typo pins nothing."""
    unknown = sorted(set(kw) - set(FINGERPRINT_FIELDS))
    if unknown:
        raise PoolError(f"unknown fingerprint fields {unknown}; "
                        f"supported are {list(FINGERPRINT_FIELDS)}")
    fp = {f: kw.get(f) for f in FINGERPRINT_FIELDS}
    if not isinstance(fp["k"], int) or fp["k"] < 1:
        raise PoolError("k must be a positive integer")
    seeds = fp["seeds"]
    if not isinstance(seeds, (list, tuple)) or len(seeds) != fp["k"]:
        raise PoolError(
            f"seeds must be an explicit list of exactly k={fp['k']} values, so "
            "the seed schedule can be pinned in a preregistration rather than "
            "being an implicit range()")
    if len(set(seeds)) != len(seeds):
        raise PoolError("duplicate seeds would make two slots the same draw")
    temps = fp["temperatures"]
    if not isinstance(temps, (list, tuple)) or len(temps) != fp["k"]:
        raise PoolError(f"temperatures must be a list of exactly k={fp['k']}")
    fp["seeds"] = list(seeds)
    fp["temperatures"] = [float(t) for t in temps]
    return fp


def fingerprint_sha256(fp: dict) -> str:
    return "sha256:" + hashlib.sha256(canonical(fp).encode()).hexdigest()


def fill(tasks: list, proposer, fingerprint: dict, out_dir) -> dict:
    """Generate exactly k candidates for every task. No early stopping, ever.

    `proposer.generate(prompt, seed=, temperature=, max_new_tokens=)` returns an
    object with `.text`. A generation failure is RECORDED in its slot and
    attributed to the harness; it is never a candidate failure and never a
    silently burned attempt.
    """
    fp = make_fingerprint(**fingerprint)
    out = Path(out_dir)
    (out / "candidates").mkdir(parents=True, exist_ok=True)
    entries = []
    for task in tasks:
        task_id = str(task.get("task_id", ""))
        if not task_id:
            raise PoolError("every task needs a task_id; a pool keyed on "
                            "position cannot be re-joined to anything")
        prompt = task.get("prompt", "")
        max_new = int(task.get("max_new_tokens") or fp["max_new_tokens"] or 512)
        slots = []
        for i in range(fp["k"]):
            seed, temp = fp["seeds"][i], fp["temperatures"][i]
            try:
                res = proposer.generate(prompt, seed=seed, temperature=temp,
                                        max_new_tokens=max_new)
                text = res.text if isinstance(res.text, str) else str(res.text)
            except Exception as e:
                # Recorded, not swallowed. A slot that never produced anything is
                # a gap in the record, and an arm reading this pool must be able
                # to exclude it from a denominator rather than grade it.
                slots.append({"slot": i, "seed": seed, "temperature": temp,
                              "candidate_sha256": None,
                              "error": f"{type(e).__name__}: {e}"[:300]})
                continue
            d = digest(text)
            path = out / "candidates" / (d.split(":", 1)[1] + ".txt")
            if not path.exists():                    # content-addressed: one copy
                path.write_text(text, encoding="utf-8")
            slots.append({"slot": i, "seed": seed, "temperature": temp,
                          "candidate_sha256": d, "error": None})
        entries.append({"task_id": task_id, "prompt_sha256": digest(prompt),
                        "slots": slots})
    doc = {"schema": SCHEMA, "fingerprint": fp,
           "fingerprint_sha256": fingerprint_sha256(fp),
           "n_tasks": len(entries), "entries": entries}
    (out / INDEX_NAME).write_text(json.dumps(doc, indent=1), encoding="utf-8")
    return doc


class Pool:
    """Read-only view of a filled pool. Arms consume this and nothing else."""

    def __init__(self, out_dir):
        self.dir = Path(out_dir)
        p = self.dir / INDEX_NAME
        if not p.exists():
            raise PoolError(f"no pool index at {p}")
        self.doc = json.loads(p.read_text(encoding="utf-8"))
        if self.doc.get("schema") != SCHEMA:
            raise PoolError(f"not a candidate pool: {self.doc.get('schema')!r}")

    @property
    def k(self) -> int:
        return self.doc["fingerprint"]["k"]

    @property
    def fingerprint_sha256(self) -> str:
        return self.doc["fingerprint_sha256"]

    def task_ids(self) -> list:
        return [e["task_id"] for e in self.doc["entries"]]

    def text(self, candidate_sha256: str) -> str:
        """Read a candidate back, verifying its digest. A cache that returns
        unverified bytes is a cache that can be edited."""
        name = candidate_sha256.split(":", 1)[-1]
        if len(name) != 64 or any(c not in "0123456789abcdef" for c in name):
            raise PoolError(f"not a sha256 digest: {candidate_sha256!r}")
        path = self.dir / "candidates" / (name + ".txt")
        if not path.exists():
            raise PoolError(f"candidate {candidate_sha256[:22]}... is missing")
        text = path.read_text(encoding="utf-8")
        if digest(text) != f"sha256:{name}":
            raise PoolError(
                f"candidate {candidate_sha256[:22]}... does not hash to its own "
                "filename; the cache has been modified")
        return text

    def slots(self, task_id: str) -> list:
        for e in self.doc["entries"]:
            if e["task_id"] == task_id:
                return e["slots"]
        raise PoolError(f"no task {task_id!r} in this pool")

    def candidates(self, task_id: str) -> list:
        """(slot, text) for every slot that produced something, in slot order."""
        return [(s["slot"], self.text(s["candidate_sha256"]))
                for s in self.slots(task_id) if s["candidate_sha256"]]

    def health(self) -> dict:
        """Per-pool generation health, so a denominator can exclude gaps."""
        total = filled = 0
        empty_tasks = []
        for e in self.doc["entries"]:
            got = sum(1 for s in e["slots"] if s["candidate_sha256"])
            total += len(e["slots"])
            filled += got
            if not got:
                empty_tasks.append(e["task_id"])
        return {"slots_total": total, "slots_filled": filled,
                "slots_failed": total - filled,
                "tasks_with_no_candidate": empty_tasks,
                "n_tasks": self.doc["n_tasks"]}

    def does_not_prove(self) -> list:
        return [
            "NOT_PROVES_GENERATION_DETERMINISM: a pool pins the generation "
            "settings, not the serving stack. Two pools from one fingerprint can "
            "differ, and this records enough to see that, not to prevent it.",
            "NOT_PROVES_CANDIDATE_CORRECTNESS: a pool holds candidates. The "
            "verdict authority is the oracle, never the cache.",
            "NOT_PROVES_TASK_REPRESENTATIVENESS: k candidates on these tasks say "
            "nothing about tasks outside this set.",
        ]
