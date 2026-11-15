"""Synthetic fixtures for the series and voice tests.

The templated set repeats one paragraph shape, one heading set, one shared
phrase and one title formula across four documents, with an even rhythm and no
first person. The varied set is four short first-person pieces with specific
names and numbers, uneven sentences and no shared shape. No private text is
used here; every sentence below was written for these tests.
"""

TEMPLATED_TITLES = ["The Ledger Is Not the Record", "The Vote Is Not the Law",
                    "The Price Was Never the Cost", "The Map Is Not the Road"]
TOPICS = ["ledger", "vote", "price", "map"]
SECTIONS = ["In short", "The money", "The rules", "The people"]


def _templated_paragraph(topic, k):
    return (f"The {topic} shows a pattern that the oversight board approved the funding again. "
            f"According to the filing, the members signed the plan without a recorded objection. "
            f"Confidence in this reading is moderate because the minutes are short. "
            f"This does not prove that the members knew the full terms of item {'abcdefgh'[k]}.")


def templated_doc(i):
    lines = [f"# {TEMPLATED_TITLES[i]}", ""]
    k = 0
    for section in SECTIONS:
        lines += [f"## {section}", ""]
        for _ in range(2):
            lines += [_templated_paragraph(TOPICS[i], k), ""]
            k += 1
    return "\n".join(lines)


def templated_docs():
    return [{"name": f"t{i}.md", "text": templated_doc(i)} for i in range(4)]


VARIED = [
    ("tacoma.md", "Tacoma in March", """# Tacoma in March

I walked from Federal Way to Tacoma on March 3 because a strike had shut down Route 500. It took me five hours. My shoes gave out near Fife, and my patience with the transit agency gave out sooner, since it posted its first update at 11 at night.

Halfway there I stopped at a diner on Pacific Highway. The waitress, a woman named Doreen who had worked there since 1988, told me that half her regulars had stopped coming in. She blamed the parking meters. I think she was partly right, though the meters went in years before the slump started.

When I reached the Tacoma Dome station the gates were locked. A guard said the trains would resume Thursday, so I sat on the curb and ate an orange I had carried the whole way from home.

I wanted to know how long the walk takes when nothing else works. Now I know. It is 22 miles and five hours, with a stop for pie.
"""),
    ("ferry.md", "Why the Ferry Runs Late", """# Why the Ferry Runs Late

My father ran the Bainbridge ferry ramp for eleven years, and he hated the schedule. He said it was written by someone who had never watched a truck back down a wet ramp in January.

The state counts a boat as late when it leaves more than ten minutes after its posted time. By that count the 7:55 sailing left late on 31 of 60 weekdays last winter. I copied the logs myself at the Colman Dock office, where a clerk let me photograph the binder on a slow Tuesday.

Loading is the slow part. A car rolls on in about 4 seconds. A semi with a nervous driver can take a full 60, and nobody on the crew wants to rush a semi on a ramp that tilts with the tide.

My guess is that the posted times are a promise the boats cannot keep in winter, and that Dad was right about who wrote them.
"""),
    ("budget.md", "A Kitchen Table Budget", """# A Kitchen Table Budget

In 2019 my partner and I started writing our budget on the back of a Safeway receipt every Sunday. It sounds silly. It worked better than any app we tried, mostly because the receipt was already on the table when we sat down to eat.

We spent $412 on groceries that first month and $388 the second. I remember the drop because Sam bought a rice cooker with the difference and named it Gerald.

Apps wanted categories. We wanted one number: how much was left until Friday?

We still do it. The receipts live in a shoebox under the bed, about 260 of them by now, and I can tell you from them which week the car broke down outside Olympia and which week Sam got the job at the library.
"""),
    ("shift.md", "Rain and the Second Shift", """# Rain and the Second Shift

I worked nights at the Boeing plant in Everett for two winters. The rain there never stops so much as it changes its mind about direction.

On the second shift the cafeteria closed at 9, so most of us brought soup in thermoses. Luis, who ran the rivet line next to mine, brought the same chicken soup for 140 nights in a row and never once complained about it to anyone on the floor.

What I remember best is the drive home at 2 in the morning on Highway 526, when the wipers made the only sound and I could think without anyone asking me for anything at all.

I left in 2014. I miss Luis and I do not miss the rain.
"""),
]


def varied_docs():
    return [{"name": name, "text": text, "title": title} for name, title, text in VARIED]


DISCLOSURE = "Drafted with Claude from the record and checked by the author."

SCAFFOLD_ESSAY = """# Who Holds the Keys

The county moved its election servers to a private vendor in 2021. Records from the procurement office show three bids. Confidence: high. This does not prove the bidding was fair.

The vendor hired two former county staff within a year, according to state lobbying filings [1]. The hires were legal under the 2019 rules. Confidence: moderate. This does not show that the hires changed any decision.

Residents asked for the audit logs at a March meeting. The county released them in June at https://example.org/logs. The logs cover 14 months.

""" + DISCLOSURE + "\n"
