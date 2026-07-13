"""scout calibration falsifier — the sly fox must see the thesis in plain words.

Real curated signal (X reposts, forum posts, blog titles) states harness-relevant
mechanisms in ORDINARY language and at VARYING length. The scout's job is to
surface those threads, not only arxiv-dense titles. Two failure modes this pins:

  B1 (length fragility): relevance was hits/word_count, so the SAME thread flipped
     ACTIONABLE<->NOISE purely on how verbosely it was phrased. A curation metric
     that depends on prose length instead of concept coverage is not measuring
     relevance. Falsifier: a terse and a verbose statement of the same thread get
     the SAME verdict.

  B2 (substring false-positives): vocab was matched with `term in text`, so
     "emergent" scored a hit for "merge". Phantom concepts inflate relevance.
     Falsifier: a word that merely CONTAINS a vocab term as a substring, at a
     non-boundary, does not count as that concept.

Criterion (external, stated — not "make it agree with me"): a thread is RELEVANT
(>= INSPIRATION) iff it names >= 2 distinct harness concepts (verification,
oracle, retrieval, local inference, memory, ...). It is ACTIONABLE iff it ALSO
carries a falsifiable/measurable claim (a metric, ablation, throughput, ...).
Market hype and unrelated tooling name no mechanism -> NOISE.
"""
import pytest

from harness.scout import assess, rank, _hit_terms, HARNESS_VOCAB

# Plain-language statements of real harness-relevant mechanisms (should surface).
RELEVANT = [
    ("verification-gate",
     "verification gates are the bottleneck, not agent count; you need a system "
     "that catches bad work and reviews the output before it ships. throughput "
     "is bounded by the oracle, not by how many agents you spawn."),
    ("harness-body",
     "the harness is the body: it lets the agent use tools, gather context, and "
     "verify its work. capability is engineered in the harness, not the raw model."),
    ("living-wiki",
     "feeds a living wiki with retrieval, backlinks and a memory that compounds "
     "over time instead of a chat tab with amnesia."),
    ("local-inference",
     "run capable models locally and offline on commodity hardware, open-source "
     "weights, no cloud and no data leaving the machine."),
]

# Market hype / unrelated tooling: names no harness mechanism (should be NOISE).
NOISE = [
    ("gpt-hype",
     "GPT drops this week and they are hyping it as a leap, fewer guardrails, "
     "usage limits you can live with, pricing pressure on everyone else."),
    ("text-to-3d",
     "learning to model in 3D takes weeks; this tool does it in seconds, you "
     "write the idea and the asset comes out ready to use."),
]


def test_no_phantom_substring_hits():
    # "emergent" must NOT count as the concept "merge"; "therapist" not "cache".
    assert "merge" not in _hit_terms("an emergent property of complex systems", HARNESS_VOCAB)
    # a real boundary match still lands (stems must keep working):
    assert any(t for t in _hit_terms("weight quantization to 4-bit", HARNESS_VOCAB)
               if "quantiz" in t)


@pytest.mark.parametrize("name,text", RELEVANT)
def test_plain_language_thesis_is_relevant(name, text):
    a = assess({"id": name, "text": text})
    assert a.verdict != "NOISE", f"{name}: plain-language thesis dropped to NOISE ({a.relevance})"


@pytest.mark.parametrize("name,text", NOISE)
def test_market_hype_is_noise(name, text):
    a = assess({"id": name, "text": text})
    assert a.verdict == "NOISE", f"{name}: hype/unrelated must be NOISE (got {a.verdict})"


def test_relevant_ranks_above_noise():
    catalog = ([{"id": n, "text": t} for n, t in RELEVANT]
               + [{"id": n, "text": t} for n, t in NOISE])
    ranked = rank(catalog)
    verdicts = [a.verdict for a in ranked]
    # every non-noise sorts before every noise
    last_relevant = max(i for i, v in enumerate(verdicts) if v != "NOISE")
    first_noise = min(i for i, v in enumerate(verdicts) if v == "NOISE")
    assert last_relevant < first_noise


def test_length_invariance_same_thread_same_verdict():
    # THE sharp one: verbosity must not change the verdict (falsifies B1).
    terse = "verification gates bound throughput, not agent count."
    verbose = (
        "here is the thing that most people building agent swarms keep getting "
        "wrong in my honest opinion after a lot of trial and error this year: "
        "the verification gates are what actually bound throughput on any real "
        "workload, not the raw number of agents you happen to spawn in an "
        "afternoon, because without a system that catches bad work you are just "
        "generating more output nobody has checked.")
    assert assess({"id": "t", "text": terse}).verdict == \
           assess({"id": "v", "text": verbose}).verdict
