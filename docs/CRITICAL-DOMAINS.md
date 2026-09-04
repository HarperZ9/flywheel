# Critical domains

Tax was the example that started this work. Tax is not the point.

A frontier model's demo filed a Form 1040 that took the tax from the rate
schedule, giving $4,165.50, where the form requires the tax table, giving
$4,169. Both figures are arithmetically correct. What went wrong was which
source got to decide.

That defect is not specific to tax, or to finance. It reaches every answer where
a number is produced by a method and a different method governs.

## The shape

| Domain | The answer is right about | It is wrong about |
| --- | --- | --- |
| Finance | the arithmetic of the rate schedule | the form requiring the tax table |
| Finance | the interest on 180 days | the instrument saying actual/365, not 30/360 |
| Finance | the amount | yen having no minor units, so the decimals cannot be paid |
| Medicine | milligrams per kilogram | the formulary banding the dose instead of computing it |
| Medicine | the number | the unit being micrograms and the answer saying milligrams |
| Medicine | the equation it ran | the protocol naming CKD-EPI and the answer running Cockcroft-Gault |
| Law | counting five days | the rule counting court days, which lands two days later |
| Law | the format of the citation | the citation not existing |
| Law | the filing | the limitations period having closed |

Every row is a value that survives self-review. Rereading the work confirms the
method that produced it, and the method is the thing under test.

## A pack ships no domain data

This is the rule the whole package rests on.

A pack carries no formulary, no rate table, no maximum dose, no statute, no
court calendar, no citation registry. Shipping any of those would ask a reader
to trust a number whose provenance is a commit message. That is the failure this
feature exists to catch, wearing a library's clothes.

What a pack ships instead:

- **Field templates.** The authority kind, the criticality, and the method
  mandate a field of this shape has in this domain.
- **A manifest.** Which sources the caller has to supply an authority for.
- **Arithmetic.** Day counts, unit conversion, rounding, business days,
  ceilings, all computed from constants the caller passes in.

The payoff is that a gap becomes loud. A critical field with no authority behind
it resolves to `AUTHORITY_UNAVAILABLE`, which is `UNVERIFIABLE`, which holds the
release. Without a pack the same gap is a field nobody thought to check.

Run `flywheel packs` to see what each one declares. The caution prints first.

## Authority kinds

| Kind | What it decides | How it fails |
| --- | --- | --- |
| `TABLE` | a value looked up in a source that supersedes any formula | the answer computed what the table decides |
| `RECOMPUTE` | a value derived a second time, independently | the two derivations disagree |
| `CITED` | nothing; it asks only that the answer name where it looked | the answer cites nothing |
| `UNIT` | which unit the value has to be in | the answer is in a different unit, or states none |
| `BOUND` | whether the value is permitted | the value is outside what the source allows |

`UNIT` and `BOUND` exist because a right number can still be wrong. A dose of
600 is correct in milligrams and a thousandfold overdose in micrograms. A dose
of 600 mg computed perfectly is still an error above a 500 mg daily ceiling.
Neither failure is reachable by comparing numbers.

A `BOUND` authority returns a permission and a reason, never a value:

```python
from harness.domain_packs.units import ceiling_authority

authorities = {"formulary:max-daily": ceiling_authority("dose", 600.0, "mg")}
```

The row that comes back says whether the dose was permitted and why. It never
carries the ceiling as a value, for the same reason feedback never carries the
authoritative number: an attempt that reads its answer out of its own failure
report has consulted nothing.

## The method mandate

A field may name the method the domain requires. The mandate is checked before
the value.

```json
{"use": "renal_function", "name": "egfr", "source": "protocol:renal-2026"}
```

The medicine pack gives that field `RECOMPUTE` and mandates `ckd-epi-2021`. An
answer that states `cockcroft-gault` fails with `METHOD_MISMATCH` even when the
two equations happen to return the same number. Those occasions are exactly the
ones that must not pass, because the answer is right by luck and will be wrong
on the next patient.

An answer that states no method at all is `METHOD_UNSTATED`, which is
`UNVERIFIABLE`. Silence about the method is not evidence the right one was used.

## Criticality and release

The verdict says whether the values are confirmed. The release decision says
whether the answer may leave the building, and it is strictly narrower.

| Criticality | A non-PASS field means |
| --- | --- |
| `advisory` | the answer ships with a caveat |
| `standard` | the answer ships with a caveat |
| `critical` | the answer is held |

Criticality never softens a verdict. A `FAIL` holds the release no matter how a
field is marked. What criticality decides is what an `UNVERIFIABLE` blocks,
because an unchecked footnote and an unchecked dose are the same verdict and not
the same risk.

Packs mark nearly everything critical. Lowering it is allowed, and it is a
decision someone should have to write down in the contract document:

```json
{"use": "dose", "name": "dose", "source": "formulary:2026-03",
 "criticality": "advisory"}
```

## finance

Six templates. `statutory_amount` is the 1040 case in general form.

| Template | Kind | Catches |
| --- | --- | --- |
| `statutory_amount` | `TABLE` | the rate schedule used where the tax table governs |
| `accrued_interest` | `RECOMPUTE` via `actual/365` | 30/360 used where the instrument says actual/365 |
| `minor_units` | `RECOMPUTE` | a yen amount carried to two decimals |
| `currency` | `UNIT` | a figure reported without saying which currency |
| `threshold` | `BOUND` | a correctly computed figure that exceeds a cap |
| `authority_cited` | `CITED` | a right number nobody can trace |

Four day-count conventions are implemented: `30/360`, `actual/360`,
`actual/365`, and `actual/actual`. The last one splits at the year boundary and
uses each year's own denominator, so a period running from December 2027 into
February 2028 is `31/365 + 31/366` rather than a single fraction. An unknown
convention raises instead of falling back to a default, because a silent default
here is how the wrong convention gets used.

Rounding is explicit. `half-up`, `half-even`, and `truncate` give 3.0, 2.0, and
2.0 on the same 2.5, and a domain that mandates one of them is not served by a
library that picked another. Minor units come from an ISO 4217 map the caller
extends; an unlisted currency raises rather than assuming two decimal places.

## medicine

Eight templates, all critical.

| Template | Kind | Catches |
| --- | --- | --- |
| `dose` | `TABLE` via `formulary-band-lookup` | a computed mg/kg figure where the formulary bands the dose |
| `dose_computed` | `RECOMPUTE` via `weight-based-mg-per-kg` | a dose derived from a weight the answer never stated |
| `dose_unit` | `UNIT` | milligrams reported where micrograms were meant |
| `maximum` | `BOUND` | an arithmetically perfect dose above the daily maximum |
| `renal_function` | `RECOMPUTE` via `ckd-epi-2021` | Cockcroft-Gault used where the protocol names CKD-EPI |
| `contraindication` | `BOUND` | a safe-looking dose for a patient who must not have it |
| `route` | `TABLE` | an oral dose given an intravenous route |
| `source_cited` | `CITED` | a plausible dose with nothing behind it |

The weight-based authority takes the milligrams per kilogram, the cap, and the
unit from the caller. It converts a weight stated in pounds before multiplying,
so an answer that gave 154 lb is compared on the same footing as one that gave
69.853 kg. The cap applies after the multiply, which is where a ceiling belongs
and is easy to get backwards.

Named equations are strings, not implementations. A contract can mandate
CKD-EPI and fail an answer that used Cockcroft-Gault without this package having
any opinion about what either equation computes.

`mmol` to `mg` is refused. The conversion needs a substance-specific molar mass,
and a library that guessed one would be inventing clinical data.

## law

Five templates.

| Template | Kind | Catches |
| --- | --- | --- |
| `deadline` | `RECOMPUTE` via `court-days` | calendar days counted where the rule counts court days |
| `service_date` | `RECOMPUTE` via `calendar-days` | a notice period counted from the wrong trigger |
| `within_period` | `BOUND` | a correctly formatted filing made after the period closed |
| `citation` | `CITED` | a citation that reads correctly and does not exist |
| `jurisdiction` | `CITED` | one state's rule applied to another state's filing |

Three counting rules: `calendar-days`, `court-days`, and `business-days`. Five
days from Friday 2026-09-04 is 2026-09-09 on calendar days and 2026-09-11 on
court days. A holiday the caller passes in pushes it further. Counting backwards
works, which is what a notice period served before a hearing needs.

Holidays are the caller's. There is no court calendar in this package, and a
jurisdiction's holiday list is a fact about that jurisdiction rather than about
day arithmetic.

Citations resolve against a registry the caller supplies. A fabricated citation
is caught by the registry declining it, not by anything in this repository
claiming to know which cases exist.

## Using a pack

From a contract document, name the pack and use a template. The document states
the two facts the pack cannot know: what the field is called, and which source
decides it.

```json
{
  "pack": "medicine",
  "fields": [
    {"use": "dose", "name": "dose", "source": "formulary:2026-03"},
    {"use": "dose_unit", "name": "dose", "source": "formulary:2026-03"},
    {"use": "maximum", "name": "dose", "source": "formulary:max-daily"}
  ],
  "authorities": {
    "formulary:2026-03": {"kind": "command", "argv": ["python", "formulary.py"]},
    "formulary:max-daily": {"kind": "command", "argv": ["python", "ceiling.py"]}
  }
}
```

From Python, where a resolver is a callable rather than a declaration:

```python
from harness.domain_packs import contract_from, load_pack, unsupplied
from harness.domain_packs.medicine import weight_based_authority
from harness.domain_packs.units import ceiling_authority
from harness.output_contract import check_answer

pack = load_pack("medicine")
contract = contract_from(pack, [
    {"use": "dose_computed", "name": "dose", "source": "protocol:2026-03"},
    {"use": "maximum", "name": "dose", "source": "protocol:max-daily"},
])
authorities = {
    "protocol:2026-03": weight_based_authority(10.0, cap=600.0),
    "protocol:max-daily": ceiling_authority("dose", 600.0, "mg"),
}
report = check_answer(answer, contract, authorities)
```

Every resolver receives the whole answer, so an authority that needs one field
has to be told which one. That is what `reads` is for.

## Knowing what will hold before you run

```python
unsupplied(contract, authorities)
```

Returns the fields whose source has no authority behind it, critical ones first.
It answers "what does nothing in this system actually check" before an expensive
attempt rather than after one.

## Post-task, post-goal, post-session

A single check answers one question about one answer. The accumulated question
is the one an operator asks: across this task, this goal, this whole session,
what went out unverified.

Each check appends a line to a ledger, and the three scopes read the same file.

```bash
flywheel check-output --contract c.json --answer a.json \
    --scope task --subject t-14 --strict
```

`--strict` puts the release decision on the exit code, for a caller that cannot
carry a caveat. A held answer exits 1 where the verdict alone would have exited
3. The verdict is unchanged.

In the loop, a lane that declares a contract gets the check on its critical
path:

```python
result = run_loop(task, proposer, oracle,
                  output_contract=contract,
                  output_authorities=authorities)
```

A held answer does not accept. The gate is on `HOLD` rather than on any
non-PASS, so a contract author sets the strictness through criticality. Reading
the ledger back:

```python
from harness.validation_ledger import outstanding, read_ledger, roll_up

roll_up(read_ledger(scope="session"))
outstanding(read_ledger(scope="session"))
```

The roll-up takes the worst entry, never the latest. A session whose last check
passed is not a clean session if something went out on hold in the middle of it.

## What these packs do not do

Stated plainly, because a safety feature that overstates its reach is worse than
none.

- They hold no domain data and never will. Every authority is the caller's.
- They do not know whether your authority is correct. A wrong tax table checked
  against itself passes.
- `CITED` confirms that a source was named. Whether that source says what the
  answer claims is the authority's job, and for citations that means a registry.
- They cover the fields they declare. A regulated answer has fields no pack
  anticipated, and those are unchecked unless you write them into the contract.
- Coverage across domains is uneven on purpose. Finance, medicine, and law are
  where the failures were legible enough to falsify. Aviation, nuclear,
  structural, and clinical-trial reporting are not covered.

## See also

- [OUTPUT-VALIDATION.md](OUTPUT-VALIDATION.md): the contract format, the checker
  protocol, and the retry loop.
- [examples/output-validation](../examples/output-validation/README.md): the
  1040 case, runnable, with both answers.
