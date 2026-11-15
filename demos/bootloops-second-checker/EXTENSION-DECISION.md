# Extension decision record, 2026-10-02

Written before any extension code. The pilot is free and unsolicited. The only
reader who decides anything is BootLoops, through one follow-up email with one
question. Each extension below is judged by what it would change in that email
or in the report the email links to.

## Baseline

The follow-up draft says three checkers agree on 12,187 locally emitted
witnesses, names four `core.py` findings from 14 hand-built inputs, and quotes a
Lean ceiling of 10,000 row terms. Two weaknesses limit what that draft can claim.
Both clean-room checkers came from one model in one session. The edge findings
come from inputs one author thought of.

## Extensions

| item | question it answers | what changes in the follow-up if it lands | what changes if it is null |
|---|---|---|---|
| 0a. `run_all.sh` in one pass on Linux | does the one-command claim hold on a second platform from a fresh clone? | the email can say the repo reproduces on Linux and Windows | the email must not claim one-command reproduction until fixed |
| 0b. corpus regenerated from seeds | are the published counts reproducible byte for byte? | the counts in the email stand on a hash check | any drift is reported, and the counts get a caveat |
| 3. checker from a different model family | do the findings survive an implementer that shares no training lineage with the first two? | "independent" in the email can mean a different model family wrote one checker from the spec alone | the report keeps "same-model" labels; the email does not use "independent" for the pair |
| 4. differential fuzzing | are there disagreements a person did not think to write down? | any new `core.py` finding goes into the report; the email still names at most the top findings | a seeded null ("N cases, 0 disagreements beyond the known classes") strengthens the existing list |
| 5. Lean past 10,000 terms | is 10,000 terms the kernel's limit or this encoding's? | the ceiling quoted in the email moves, or the email says where it stops and why | the 10,000 figure stays, now with the reason it stops |
| 6. recheck for published witnesses | has BootLoops published witness files or system snapshots since the first search? | real witnesses replace synthetic ones as the headline result | the "no published witnesses" statement is refreshed with today's date |
| 7. statement-fidelity table for the Lean modules | does the Lean statement say what the witness format says? | the Lean claim in the email is bounded by any gap found | the report records the mapping as a model-made review with no gaps found |

## Decision

Item 7 was requested before this record was written. The axiom audit with a
planted extra-axiom control was requested after it, during the work, and is
reported in REPORT.md section 13 with item 5.

Do all seven, in that order, and keep nulls. The follow-up email keeps its one
question. Extensions change the evidence behind its sentences and leave its
length alone; the draft must stay under 200 words, so most results live in
REPORT.md only.

Limits stated up front: the new checker is model-written, and "different model
family" is not the same as an independent human team. The fuzzer finds
disagreements; it does not decide which reading of the spec is right.
