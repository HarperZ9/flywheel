"""A checker program, speaking the command-authority protocol.

Not a tax authority and not filing advice. It models one rule so the example
can be run end to end: below the table's ceiling the tax is read off a row $50
wide, computed on the midpoint of that row, and rounded to whole dollars. That
rule is the entire reason the table and the rate schedule disagree. At a taxable
income of $36,700 the schedule charges tax on $36,700 and the table charges it
on $36,725.

    the rate schedule  ->  $4,165.50    what the demo filed
    the tax table      ->  $4,169       what the form requires

Coverage is narrower than the real table at both ends, and this declines outside
it rather than extrapolating. Guessing past the edge would publish a fabrication
with a checker's authority behind it.

The protocol, which is all a checker has to meet:

    stdin      the answer, as JSON
    stdout     {"value": ...}, as JSON
    exit 0     the value on stdout decides this field
    exit 3     this input is outside what the program covers
    anything   the program broke, and the field goes unchecked
"""
import json
import sys
from decimal import ROUND_HALF_UP, Decimal

ROW_WIDTH = Decimal("50")

# (ceiling, rate) for a 2025 single filer, lowest two brackets only.
BRACKETS = ((Decimal("11925"), Decimal("0.10")),
            (Decimal("48475"), Decimal("0.12")))
FLOOR = Decimal("5000")
CEILING = BRACKETS[-1][0]


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
        raise LookupError(f"this example covers taxable income from ${FLOOR:,.0f} "
                          f"to ${CEILING:,.0f}, and was asked for ${income:,.2f}")
    midpoint = (income // ROW_WIDTH) * ROW_WIDTH + ROW_WIDTH / 2
    return int(schedule(midpoint).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def main() -> int:
    answer = json.load(sys.stdin)
    income = (answer.get("taxable_income") or {}).get("value")
    if income is None:
        print("the answer states no taxable income to look up", file=sys.stderr)
        return 3
    try:
        value = table(income)
    except LookupError as exc:
        print(exc, file=sys.stderr)
        return 3
    print(json.dumps({"value": value}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
