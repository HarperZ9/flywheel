"""Plain-words views of a voice profile and a voice comparison.

describe turns each stored field into sentences an author can check against
their own sense of how they write. Each line starts with the field name so the
author can match it to the stored JSON.
"""

_CLASS_WORDS = {"i": "I or my", "we": "we or our", "pronoun": "a pronoun such as it or they",
                "conjunction": "a joining word such as and, but or so",
                "adverb": "an adverb such as then or still", "article": "a, an or the",
                "question_word": "a question word", "number": "a number", "other": "another word"}


def _one_in(share):
    if not share:
        return "none of your sentences"
    n = round(1 / share)
    return "almost every sentence" if n <= 1 else f"about 1 sentence in {n}"


def _sources(p):
    src = p["sources"]
    line = (f"sources: built from {len(src['samples'])} samples, {src['total_words']:,} words "
            "in all. The profile keeps a fingerprint and a word count for each sample and "
            "none of their text.")
    if src["indicative_only"]:
        line += " That is under 5,000 words, so treat every comparison as indicative only."
    return [line]


def _rhythm(p):
    r = p["rhythm"]
    q, pq = r["sentence_quantiles"], r["paragraph_quantiles"]
    return [f"rhythm: In your samples, the middle sentence runs {q['50']} words, and half of "
            f"your sentences run between {q['25']} and {q['75']} words.",
            f"rhythm: Your middle paragraph runs {pq['50']} words. The sentence length "
            f"variation (CV) is {r['sentence_cv']}, and the paragraph length variation is "
            f"{r['paragraph_cv']}."]


def _openings(p):
    classes = p["openings"]["classes"]
    lines = [f"openings: In your samples, {_one_in(share)} opens with {_CLASS_WORDS[c]}."
             for c, share in sorted(classes.items(), key=lambda kv: -kv[1]) if share]
    top = ", ".join(list(p["openings"]["top_words"])[:15])
    if top:
        lines.append(f"openings: Your most common opening function words are {top}.")
    return lines


def _argument(p):
    a = p["argument"]
    return [f"argument: Per 1,000 words you use first person singular {a['first_person_per_1k']} "
            f"times and we or our {a['author_we_per_1k']} times.",
            f"argument: Per 1,000 words you ask {a['questions_per_1k']} questions and use "
            f"{a['contractions_per_1k']} contractions and {a['hedges_per_1k']} hedge words.",
            f"argument: Per 1,000 words you concede (but, though, yet) {a['concession_per_1k']} "
            f"times, give a cause (because, so, since) {a['causal_per_1k']} times and set a "
            f"condition (if, unless) {a['conditional_per_1k']} times."]


def _function_words(p):
    top = ", ".join(list(p["function_words"])[:8])
    return [f"function_words: The profile stores how often you use {len(p['function_words'])} "
            f"common function words, led by {top}. It stores no content word in this field."]


def _vocabulary(p):
    v = p.get("vocabulary")
    if v is None:
        return []
    words = ", ".join(v["words"][:20]) or "none yet"
    return [f"vocabulary: {len(v['words'])} words you use 3 or more times across 2 or more "
            f"samples, with names of people and places left out: {words}. The comparison "
            "is against your own samples only. Learn with --no-vocabulary to leave this out."]


def _per_sample(p):
    return [f"per_sample: The same measures for each of your {len(p['per_sample'])} samples, "
            "so a comparison can use the spread across your samples."]


def describe(profile):
    lines = []
    for part in (_sources, _rhythm, _openings, _argument, _function_words, _vocabulary,
                 _per_sample):
        lines += part(profile)
    return lines


def format_compare(report):
    out = []
    for f in report["features"]:
        out.append(f"{f['feature']}: draft {f['value']}, your range {f['low']} to {f['high']}, "
                   f"{f['verdict']}")
    for loc in report["locations"]:
        measure = ", ".join(f"{k} {v}" for k, v in loc["measure"].items())
        out.append(f"lines {loc['line_start']}-{loc['line_end']}: {loc['kind']} ({measure})")
    if report["indicative_only"]:
        out.append("The profile rests on under 5,000 words, so read these as indicative only.")
    out.append(report["scope"])
    return "\n".join(out)
