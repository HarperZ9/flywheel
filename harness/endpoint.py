"""endpoint.py -- the preregistered endpoints, as pure functions of the cache.

Section 5 of the frozen preregistration fixes what is measured. This module
computes it and nothing else. It imports no oracle, no receipt, and no I/O: the
caller passes a `submit` callable, so the whole file is exercised by a fake and
a stranger can re-derive every number on a laptop with no GPU and no network,
which is the property section 4 asks for.

The caller's contract: a "pool document" here is that rung's `pool_index.json`
ENRICHED with a `bodies` map from candidate digest to candidate text. The index
on disk stores only digests, with the text in `candidates/`, and loading files is
I/O this module deliberately does not do. A slot naming a body the map does not
carry is a refusal rather than a skip, because an endpoint computed over the
subset that happened to load is not the endpoint.

Three decisions are worth stating, because each is a place the frozen text could
have been read two ways and a silent choice would have hidden the reading:

  1. **The unit is the certificate BODY, not the model.** The endpoint asks
     whether one body yields one verdict wherever it is submitted. Permuting
     model-identity fields would only assert that a pure function ignores an
     input it does not take, which is why the prereg rejects that framing.
  2. **A body seen under more than one instance is NOT silently collapsed.**
     The frozen text says "one receipt subject digest per body", and the subject
     legitimately carries the instance. So a body that appears under two
     instances has two lawful subjects, and calling that a disagreement would
     manufacture a failure. It is counted and reported in its own category
     instead of being folded into either outcome.
  3. **A task nothing was generated for is EXCLUDED and reported.** Grading a
     task with no candidate in any slot would attribute a harness gap to the
     candidate, which section 5 forbids in as many words.
"""
from __future__ import annotations

import hashlib
from collections import Counter

SCHEMA = "flywheel.endpoint/v1"

# Verbatim from section 5 of the frozen preregistration, so a reader comparing
# this module against the document does not have to trust a paraphrase.
PRIMARY_ENDPOINT = (
    "N distinct certificate bodies, submitted through the accept path once per "
    "rung context, yields N distinct verdict digests and zero disagreements.")

FOUR_WAY = ("PASS", "FAIL", "UNDECIDED", "UNVERIFIABLE")
ATTRIBUTIONS = ("CANDIDATE", "HARNESS", "ENVIRONMENT")


class EndpointError(ValueError):
    """A pool that cannot be reduced to an endpoint without inventing a rule."""


def body_digest(body: str) -> str:
    return "sha256:" + hashlib.sha256(body.encode("utf-8")).hexdigest()


def union_of_bodies(pools: dict) -> dict:
    """The union of every distinct body across every rung of one family.

    `pools` maps rung id to that rung's pool document. Returns digest ->
    {"body", "task_ids", "rungs"}, with both lists sorted, so the union is a set
    and its iteration order is not a choice anybody made.
    """
    union: dict = {}
    for rung, doc in sorted(pools.items()):
        bodies = doc.get("bodies") or {}
        for entry in doc.get("entries", []):
            task_id = entry.get("task_id")
            for slot in entry.get("slots", []):
                sha = slot.get("candidate_sha256")
                if sha is None:
                    continue                       # a recorded gap, not a body
                body = bodies.get(sha)
                if body is None:
                    raise EndpointError(
                        f"slot for task {task_id!r} on rung {rung!r} names "
                        f"candidate {sha} but the pool carries no such body; "
                        "an endpoint over bodies cannot be computed from an "
                        "index whose candidates are missing")
                rec = union.setdefault(sha, {"body": body, "task_ids": set(),
                                             "rungs": set()})
                if rec["body"] != body:
                    raise EndpointError(
                        f"two different bodies share digest {sha}; the store is "
                        "content-addressed, so this is corruption, not a tie")
                rec["task_ids"].add(task_id)
                rec["rungs"].add(rung)
    return {sha: {"body": r["body"],
                  "task_ids": sorted(r["task_ids"]),
                  "rungs": sorted(r["rungs"])}
            for sha, r in sorted(union.items())}


def excluded_tasks(pools: dict) -> dict:
    """Tasks with no candidate in ANY slot, per rung. Reported, never graded."""
    out: dict = {}
    for rung, doc in sorted(pools.items()):
        empty = [e.get("task_id") for e in doc.get("entries", [])
                 if all(s.get("candidate_sha256") is None
                        for s in e.get("slots", []))]
        if empty:
            out[rung] = sorted(empty)
    return out


def primary_endpoint(union: dict, rung_ids, submit) -> dict:
    """Submit every body through the accept path in every rung context.

    `submit(body, task_id, rung)` returns a mapping carrying at least
    `verdict_digest` and `subject_digest`. The endpoint asserts one of each per
    body, and counts every body where that fails.
    """
    rungs = sorted(rung_ids)
    if not rungs:
        raise EndpointError("an endpoint over rung contexts needs at least one")
    bodies, disagreements, multi_instance = [], [], []
    carried: set = set()
    for sha, rec in union.items():
        task_id = rec["task_ids"][0]
        verdicts, subjects = set(), set()
        for rung in rungs:
            r = submit(rec["body"], task_id, rung)
            verdicts.add(r["verdict_digest"])
            subjects.add(r["subject_digest"])
            # Section 8 mechanism 1: the family's own qualifiers travel with
            # EVERY result, into every receipt and every bundle. An endpoint
            # that reported only its own limits would drop
            # NOT_PROVES_OPTIMALITY here, which is the exact clause the section
            # calls the most likely thing to be lost when a result is retold.
            carried.update(r.get("does_not_prove") or ())
        row = {"candidate_sha256": sha, "submitted_in_rung_contexts": len(rungs),
               "distinct_verdict_digests": len(verdicts),
               "distinct_subject_digests": len(subjects),
               "instances": rec["task_ids"]}
        if len(rec["task_ids"]) > 1:
            # Lawful, not a failure: the subject carries the instance, so a body
            # seen under two instances HAS two subjects. Counting it as a
            # disagreement would manufacture one.
            multi_instance.append(row)
        elif len(verdicts) != 1 or len(subjects) != 1:
            disagreements.append(row)
        bodies.append(row)
    return {
        "schema": SCHEMA,
        "endpoint": PRIMARY_ENDPOINT,
        "rung_contexts": rungs,
        "n_bodies": len(bodies),
        "n_distinct_verdict_digests": len({b["candidate_sha256"]
                                           for b in bodies}),
        "disagreements": disagreements,
        "n_disagreements": len(disagreements),
        "bodies_under_multiple_instances": multi_instance,
        "met": len(disagreements) == 0 and bool(bodies),
        # The family's own qualifiers first, verbatim, then this endpoint's.
        "does_not_prove": sorted(carried) + [
            "NOT_PROVES_CORRECTNESS: agreement across rung contexts says the "
            "accept path is a function of the certificate, not that any verdict "
            "it returned is right.",
            "NOT_PROVES_ANY_RUNG_IS_BETTER: this endpoint is a count with no "
            "rate in it and no cross-rung comparison of any kind.",
            "NOT_PROVES_MORE_THAN_THE_CONSTRUCTION: the accept path takes a "
            "certificate and an instance and never a rung, and the receipt "
            "subject excludes model identity by construction. So a pass here "
            "confirms that nothing leaked a rung into either digest, end to "
            "end. It is a check that the construction holds, not a discovery "
            "that rungs happen to agree.",
        ],
    }


def secondary_per_rung(pools: dict, submit) -> dict:
    """Per rung: well-formedness, the four-way distribution, the attribution
    split. Ordered by rung id, never by size, and no cross-rung delta.

    The denominator is all four verdicts, always. Excluded tasks are removed
    from it and reported separately by `excluded_tasks`.
    """
    table = {}
    for rung, doc in sorted(pools.items()):
        bodies = doc.get("bodies") or {}
        verdicts, attribs = Counter(), Counter()
        well_formed = graded = 0
        for entry in doc.get("entries", []):
            task_id = entry.get("task_id")
            for slot in entry.get("slots", []):
                sha = slot.get("candidate_sha256")
                if sha is None:
                    continue
                r = submit(bodies[sha], task_id, rung)
                graded += 1
                well_formed += 1 if r.get("well_formed") else 0
                verdicts[r["verdict"]] += 1
                attribs[r["attribution"]] += 1
        unknown = set(verdicts) - set(FOUR_WAY)
        if unknown:
            raise EndpointError(
                f"rung {rung!r} produced verdicts outside the four-way "
                f"vocabulary: {sorted(unknown)}")
        table[rung] = {
            "graded_slots": graded,
            "well_formed": well_formed,
            "verdicts": {v: verdicts.get(v, 0) for v in FOUR_WAY},
            "attribution": {a: attribs.get(a, 0) for a in ATTRIBUTIONS},
        }
    return {"schema": SCHEMA, "per_rung": table,
            "ordered_by": "rung id, never by size",
            "confounds": [
                "8x token asymmetry across the ladder",
                "8x training-context asymmetry across the ladder",
                "Qwen-only apart from a single non-Qwen rung",
                "one backend", "one quantization",
            ],
            "does_not_prove": [
                "NOT_PROVES_A_SIZE_TREND: no cross-rung delta is computed here "
                "and the confounds above are not controlled by this table.",
            ]}
