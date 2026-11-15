"""Cross-sentence devices: each named tell fires on its shape, stays quiet on
ordinary prose, and each working device is found where it is."""
from articulate import voice_devices as vd

TEMPLATE = """The ferry line.

Let's just say the ferry line.

Ran the night boats. Fixed the engines. Kept the schedule. Paid the crews.

Were called "vital." Were called "partners." Were called "heroes."

Then the county made a phone call.

They learned the thing every contractor learns:

The contract was real.

The terms were never the point.

They were the rent.

First: the route is declared essential.

Second: the subsidy arrives.

Third: the subsidy moves.

This is not a secret.

The pattern is the policy.
"""

PLAIN = """I rode the 6:10 ferry from Bremerton on 4 March 2025, and it left eleven minutes late.
The county report for that quarter lists 212 late departures, which surprised me less than it
should have. My neighbour says the crews are short, and from her side the delays look like a
staffing problem more than a scheduling one. What if the county hired twenty deckhands next
spring? I think the late count would fall, but I would want the next report before I said so.
Would you ride it?
"""


def ids(text):
    return {h["id"] for h in vd.analyze(text)["tells"]}


def test_template_post_trips_each_named_tell():
    found = ids(TEMPLATE)
    for tell in ("one-line-paragraphs", "reveal-setup", "fragment-run", "anaphora-run",
                 "colon-drumroll", "aphorism-line", "numbered-escalation", "closing-maxim"):
        assert tell in found, tell


def test_plain_paragraph_trips_none():
    assert ids(PLAIN) == set()


def test_plain_paragraph_carries_the_working_devices():
    counts = vd.analyze(PLAIN)["counts"]
    for work in ("anchor", "counter-view", "other-shoes", "what-if", "stance", "turn",
                 "reader-question"):
        assert counts[work] >= 1, work


def test_split_antithesis_across_sentences():
    assert "split-antithesis" in ids("Reading that record is not cynicism. It is basic literacy.")
    assert "split-antithesis" in ids("That's not faith. That's hypocrisy.")
    assert "split-antithesis" in ids("The facts don't change between readings. Only the story does.")
    assert "split-antithesis" not in ids("I didn't sleep last night. It was loud on the street.")


def test_epistrophe_and_tricolon():
    assert "epistrophe-run" in ids("Cats aren't going anywhere. Dogs aren't going anywhere. "
                                   "Birds aren't going anywhere.")
    assert "tricolon" in ids("The vote was managed, shaped, and constrained throughout the year.")
    assert "tricolon" in ids("It happened enough times, in enough towns, across enough decades.")
    assert "tricolon" in ids("It names the one-line paragraphs, the repeated openers and the closing maxim.")
    assert "tricolon" not in ids("We tested it in Japan, Korea and Germany last year.")
    assert "tricolon" not in ids("If the answer is nothing, is that conviction, or something else?")


def test_hedges_counted():
    hits = [h for h in vd.analyze("This is perhaps the cause. It might also be noise.")["tells"]
            if h["id"] == "hedge"]
    assert len(hits) == 2


def test_lines_point_at_the_sentence():
    hits = {h["id"]: h["line"] for h in vd.analyze(TEMPLATE)["tells"]}
    assert hits["numbered-escalation"] == 19
    assert hits["closing-maxim"] == 27


def test_bold_one_line_aphorism():
    assert "aphorism-line" in ids("Some context here for the reader.\n\n**The map is the territory.**\n")
