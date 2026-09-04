"""The authority the output-contract falsifiers are checked against.

A fixture, not a tax authority, and not filing advice. It exists because the
case it models is the clearest published example of the failure `harness/
output_contract.py` was written for: a demo filled out a Form 1040 with tax
computed from the rate schedule when the form requires the tax table, and the
two disagree by $3.50 on the income shown.

The rule rather than a transcription. Below the table's ceiling the tax is read
off a row $50 wide, computed on the midpoint of that row, and rounded to whole
dollars. That is the whole reason the table and the schedule disagree: at
$36,700 the schedule charges tax on $36,700 and the table charges it on
$36,725.

Two figures the case turns on, and this fixture reproduces both from the
brackets rather than storing them:

    schedule($36,700)  ->  $4,165.50    what the demo wrote
    table($36,700)     ->  $4,169       what the form requires

Coverage is narrower than the real table at both ends, and the fixture declines
outside it rather than extrapolating. The top stops at the second bracket,
because those are the two brackets the case sits in and the two that can be
checked by hand. The bottom stops at $5,000, because the real table's lowest
rows are narrower than $50 and this fixture does not model them: applied at $0
the $50 rule charges $3 where the table charges nothing. Declining is the
honest answer there, and it is also where the falsifier for an input the
authority does not cover gets its input.
"""
from decimal import ROUND_HALF_UP, Decimal

TABLE_ID = "irs-2025-tax-table-single"
SCHEDULE_ID = "irs-2025-rate-schedule-single"
ROW_WIDTH = Decimal("50")

# (ceiling, rate) for the 2025 single filer, lowest two brackets only.
BRACKETS = ((Decimal("11925"), Decimal("0.10")),
            (Decimal("48475"), Decimal("0.12")))
CEILING = BRACKETS[-1][0]
FLOOR = Decimal("5000")


def schedule(taxable_income) -> Decimal:
    """Tax from the rate schedule: exact, unrounded, on the income itself."""
    income = Decimal(str(taxable_income))
    tax = Decimal(0)
    lower = Decimal(0)
    for ceiling, rate in BRACKETS:
        if income <= lower:
            break
        tax += (min(income, ceiling) - lower) * rate
        lower = ceiling
    return tax


def table(taxable_income) -> int:
    """Tax from the table: the midpoint of the $50 row, to whole dollars."""
    income = Decimal(str(taxable_income))
    if income < FLOOR or income > CEILING:
        raise LookupError(f"this fixture covers taxable income from ${FLOOR:,.0f} "
                          f"to ${CEILING:,.0f}, and was asked for ${income:,.2f}")
    midpoint = (income // ROW_WIDTH) * ROW_WIDTH + ROW_WIDTH / 2
    return int(schedule(midpoint).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def tax_table_authority(answer: dict):
    """The authority as `output_contract` calls it: a function of the answer."""
    income = (answer.get("taxable_income") or {}).get("value")
    if income is None:
        raise LookupError("the answer states no taxable income to look up")
    return table(income)


def _main() -> int:
    """The same rule, speaking the command-authority protocol.

    Here so the CLI falsifiers exercise a real separate process rather than a
    stub. A checker is only independent if it actually runs on its own, and a
    test that fakes the subprocess is testing the fake.
    """
    import json
    import sys

    answer = json.load(sys.stdin)
    try:
        value = tax_table_authority(answer)
    except LookupError as exc:
        print(exc, file=sys.stderr)
        return 3
    print(json.dumps({"value": value}))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
