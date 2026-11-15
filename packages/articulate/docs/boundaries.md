# What results mean

This page says what each Articulate result covers. Read it before you act on a
verdict or a receipt.

## A finding shows a writing pattern

Articulate finds writing patterns and shows where they are. Use it to improve
writing. Use other evidence to decide who wrote a text.

On 183 texts of known origin, Articulate flagged all 84 AI texts and 57 of 75
human texts (76%, 95% interval 65% to 84%). The human texts include 10 of 18
essays by English learners. The figures and the method are in the
[known-provenance results](../corpus/provenance/README.md) and
[`results.json`](../corpus/provenance/results.json).

A finding, a verdict, a texture score and a per-paragraph flag each name devices
in the text. Teachers: use them to help a student improve a draft. Use other
evidence to judge who wrote an essay. In this sample, learner English was flagged
at a lower rate than other student essays (10 of 18 against 31 of 36). Both rates
are high, and the sample is small.

## Articulate improves writing quality

Articulate finds where prose uses a named device or breaks a plain-writing
standard. It then helps you rewrite to that standard. The rewrite loop is gated
on writing quality. The benchmark reports writing quality only, and it refuses to
report a result against another detector as a feature.

## A clean screen covers the prose

For a proof or a scientific paper, a clean gate, a low texture score or a `Match`
receipt means that a named ruleset screened the prose. The theorem or the result
needs its own check. A false proof can screen as clean as a correct one. Referee
review or a machine-checked proof in a proof assistant such as Lean, Coq or
Isabelle establishes correctness.

## A receipt records a screening

A receipt records three facts. A named, fingerprinted ruleset ran on a specific
text. It gave a specific verdict. The same screening gives the same verdict when
you run it again on the same text. The verdict set is `Match`, `Drift` or
`Unverifiable`. Use a receipt to show which rules ran on which text. For
provenance, use a C2PA content credential. For EU AI Act Article 50 marking, use
a marking made for that purpose.

## A content-free receipt keeps rules and lines

A content-free audit receipt keeps no verbatim text. It drops the matched
substring and the exact offsets. It keeps the rule that fired and the line. For a
closed-vocabulary rule, the rule narrows the flagged word to that rule's small,
public word list. Use a content-free record when you must keep a screening
without the source text.

## Hash mode supports an equality check

A `--redact hash` receipt keeps a plain sha256 of each matched substring. Use it
to check a string you already know. Most rules use a public, closed word list, so
a holder can hash that list and find the flagged word. Use `--redact drop` when
the flagged word must stay secret.

## Short texts read unverifiable

A text under 30 words has too few tokens for a clean verdict. A device-clean short
text reads `unverifiable`, and its receipt makes no clean claim. A banned device
is clear at any length, so a short text with a device still reads `flagged`.

## English patterns, read with rules

The detector's patterns are English literals. On a document in another language,
the English rules run as usual. A clean result there means the English rules
found no match. Check other languages with a checker made for them.

The detector reads devices, register and structure with regular expressions.
Each finding names its rule, so you can see why it fired. The detector does not
read token probability, so a device-clean passage of machine writing can score
low. A statistical detector measures a different property, and the two methods
complement each other.
