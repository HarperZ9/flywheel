"""units.py -- unit and rounding arithmetic, with no domain knowledge in it.

Everything here is arithmetic over published conventions, so a pack may ship it
without inventing anything. Conversion factors are exact by definition for the
metric families and exact by international agreement for the customary ones.

What is deliberately absent: any conversion that needs a substance to perform.
Milligrams per decilitre and millimoles per litre describe the same quantity
only once you know the molar mass, and a molar mass is clinical data. Asking
for that conversion raises `LookupError`, which the contract turns into
OUT_OF_RANGE and then into UNVERIFIABLE. A pack that guessed instead would be
the exact failure this feature exists to catch.
"""
from __future__ import annotations

from decimal import ROUND_DOWN, ROUND_HALF_EVEN, ROUND_HALF_UP, Decimal

# Each family maps a unit to how many base units it is worth. The base unit is
# whichever one has the factor 1.
FAMILIES: dict[str, dict[str, float]] = {
    "mass": {"kg": 1000.0, "g": 1.0, "mg": 1e-3, "mcg": 1e-6, "ug": 1e-6,
             "ng": 1e-9, "lb": 453.59237, "oz": 28.349523125},
    "volume": {"L": 1.0, "dL": 0.1, "mL": 1e-3, "uL": 1e-6, "mcL": 1e-6},
    "time": {"d": 86400.0, "h": 3600.0, "min": 60.0, "s": 1.0, "ms": 1e-3},
    "length": {"km": 1000.0, "m": 1.0, "cm": 0.01, "mm": 1e-3,
               "ft": 0.3048, "in": 0.0254, "mi": 1609.344},
    "substance": {"mol": 1.0, "mmol": 1e-3, "umol": 1e-6, "mcmol": 1e-6},
}

# Rounding modes named the way a regulation names them.
HALF_UP = "half-up"
HALF_EVEN = "half-even"
TRUNCATE = "truncate"
_MODES = {HALF_UP: ROUND_HALF_UP, HALF_EVEN: ROUND_HALF_EVEN,
          TRUNCATE: ROUND_DOWN}

# ISO 4217 minor-unit digits. Short on purpose. A currency that is not listed
# raises rather than defaulting to two, because a silent default is how a
# yen amount acquires a hundredth.
MINOR_UNITS: dict[str, int] = {
    "USD": 2, "EUR": 2, "GBP": 2, "CAD": 2, "AUD": 2, "CHF": 2, "CNY": 2,
    "MXN": 2, "INR": 2, "BRL": 2, "SEK": 2, "NOK": 2, "DKK": 2, "PLN": 2,
    "JPY": 0, "KRW": 0, "CLP": 0, "ISK": 0, "VND": 0, "HUF": 0,
    "BHD": 3, "IQD": 3, "JOD": 3, "KWD": 3, "OMR": 3, "TND": 3,
}


def family_of(unit: str) -> str:
    """Which family a unit belongs to. Raises `LookupError` when none does."""
    for name, members in FAMILIES.items():
        if unit in members:
            return name
    raise LookupError(f"no known family contains the unit {unit!r}")


def convert(value: float, frm: str, to: str) -> float:
    """Convert within one family.

    Refuses across families rather than guessing a bridge. Litres do not become
    grams without a density, and millimoles do not become milligrams without a
    molar mass.
    """
    source, target = family_of(frm), family_of(to)
    if source != target:
        raise LookupError(
            f"{frm} is a {source} unit and {to} is a {target} unit, and "
            f"bridging them needs a substance-specific constant this does not "
            f"hold")
    return float(value) * FAMILIES[source][frm] / FAMILIES[target][to]


def round_to(value, places: int, mode: str = HALF_UP) -> float:
    """Round the way a rule says to round.

    Payroll and tax rules name half-up. Accounting standards often name
    half-even. Getting the wrong one is a cent per row and a reconciliation
    failure at scale, so the mode is never assumed by a caller that cares.
    """
    if mode not in _MODES:
        raise LookupError(f"unknown rounding mode {mode!r}; "
                          f"known: {sorted(_MODES)}")
    quantum = Decimal(1).scaleb(-places)
    return float(Decimal(str(value)).quantize(quantum, rounding=_MODES[mode]))


def minor_units(currency: str) -> int:
    """How many decimal places this currency has, per ISO 4217."""
    try:
        return MINOR_UNITS[currency.upper()]
    except KeyError:
        raise LookupError(
            f"{currency!r} is not in the short ISO 4217 table this ships; "
            f"supply its minor-unit digits rather than assuming two") from None


def unit_authority(required: str):
    """A UNIT authority that mandates one unit.

    The resolver ignores the answer because the mandate does not depend on it.
    The contract compares what the answer says it is measured in against what
    comes back from here.
    """
    def resolve(_answer: dict) -> str:
        return required
    return resolve


def ceiling_authority(reads: str, limit: float, unit: str, *,
                      inclusive: bool = True):
    """A BOUND authority for a ceiling the caller supplies.

    `reads` names the field in the answer to compare, because a resolver is
    handed the whole answer and a ceiling applies to one value in it.

    The limit is the caller's, because a maximum dose or a statutory cap is
    domain data and this module holds none. What it contributes is the
    comparison, the unit conversion, and the failure text.
    """
    def resolve(answer: dict):
        claim = (answer or {}).get(reads)
        if not isinstance(claim, dict) or claim.get("value") is None:
            raise LookupError(f"the answer states no value for {reads!r}")
        stated = claim.get("unit") or unit
        amount = float(claim["value"])
        if stated != unit:
            amount = convert(amount, stated, unit)
        ok = amount <= limit if inclusive else amount < limit
        if ok:
            return True, f"within the ceiling of {limit} {unit}"
        edge = "at most" if inclusive else "below"
        return False, f"{reads} must be {edge} {limit} {unit}"
    return resolve
