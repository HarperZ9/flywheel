"""medicine.py -- the medical pack.

This pack holds no clinical knowledge and that is deliberate.

No formulary, no maximum doses, no interaction list, no renal equation. A
library that shipped a dose ceiling would be asking a reader to trust a number
whose provenance is a commit message, which is precisely the failure the output
contract exists to catch. The clinical constants come from the caller, from a
source the caller can name in a report.

What the pack contributes is the shape of the check. A prescription answer has
a dose, a unit, a ceiling, a route, a frequency, and a source, and every one of
them is critical. Declaring them means an answer that omits the unit, or is
computed by an equation the protocol does not use, or has no formulary behind
it at all, reaches HOLD instead of reaching a patient.

Named equations are strings here, not implementations. A field can mandate
CKD-EPI and a contract can fail an answer that used Cockcroft-Gault, without
this module having an opinion about what either one computes.
"""
from __future__ import annotations

from ..contract_terms import BOUND, CITED, RECOMPUTE, TABLE, UNIT
from .pack import Pack, Template
from .units import HALF_UP, convert, round_to

# Method names a field may mandate. The two renal equations disagree by enough
# to change a dose, so which one the protocol names is a fact about the
# protocol and never a detail.
COCKCROFT_GAULT = "cockcroft-gault"
CKD_EPI_2021 = "ckd-epi-2021"
MDRD = "mdrd"
BSA_DUBOIS = "bsa-du-bois"
BSA_MOSTELLER = "bsa-mosteller"
WEIGHT_BASED = "weight-based-mg-per-kg"
BAND_LOOKUP = "formulary-band-lookup"
EQUATIONS = (COCKCROFT_GAULT, CKD_EPI_2021, MDRD, BSA_DUBOIS, BSA_MOSTELLER,
             WEIGHT_BASED, BAND_LOOKUP)


def weight_based_authority(per_kg: float, *, reads_weight: str = "weight",
                           unit: str = "mg", cap: float | None = None,
                           places: int = 1, mode: str = HALF_UP):
    """A RECOMPUTE authority for milligrams per kilogram, with an optional cap.

    Every clinical number in this is the caller's: the milligrams per kilogram,
    the cap, and the unit. The arithmetic and the cap being applied after the
    multiply rather than before are what the pack contributes.

    The weight is read from the answer and converted, so an answer that stated
    a weight in pounds is compared on the same footing rather than silently
    treated as kilograms.
    """
    def resolve(answer: dict):
        claim = (answer or {}).get(reads_weight)
        if not isinstance(claim, dict) or claim.get("value") is None:
            raise LookupError(f"the answer states no {reads_weight!r}")
        stated = claim.get("unit") or "kg"
        kilograms = float(claim["value"])
        if stated != "kg":
            kilograms = convert(kilograms, stated, "kg")
        dose = per_kg * kilograms
        if cap is not None:
            dose = min(dose, cap)
        return round_to(dose, places, mode)
    return resolve


def absent_authority(source: str):
    """An authority that reports it has nothing, for a source not yet wired.

    Better than leaving the source out of the map, because the report then says
    which source is missing instead of saying an authority was not supplied.
    The verdict is the same UNVERIFIABLE either way, and on a critical field it
    holds either way.
    """
    def resolve(_answer: dict):
        raise LookupError(f"{source} is declared but no authority is connected "
                          f"to it, so nothing here decides this field")
    return resolve


CAUTION = (
    "This pack is not a clinical authority and holds no clinical data. It "
    "carries no doses, no ceilings, no interactions and no equations. Every "
    "number comes from an authority the caller supplies and can name. Its "
    "contribution is that a missing authority on a critical field holds the "
    "answer instead of letting it through unchecked."
)

PACK = Pack(
    name="medicine",
    describes="clinical answers: dosing, renal function, contraindications",
    caution=CAUTION,
    templates={
        "dose": Template(
            "dose", TABLE, method=BAND_LOOKUP,
            describes="a dose the formulary decides",
            catches="a computed milligrams-per-kilogram figure used where the "
                    "formulary bands the dose"),
        "dose_computed": Template(
            "dose_computed", RECOMPUTE, method=WEIGHT_BASED,
            describes="a weight-based dose, recomputed from the stated weight",
            catches="a dose derived from a weight the answer never stated"),
        "dose_unit": Template(
            "dose_unit", UNIT, unit="mg",
            describes="the unit the dose is measured in",
            catches="milligrams reported where micrograms were meant"),
        "maximum": Template(
            "maximum", BOUND,
            describes="whether the dose is inside the ceiling",
            catches="an arithmetically perfect dose above the daily maximum"),
        "renal_function": Template(
            "renal_function", RECOMPUTE, method=CKD_EPI_2021,
            describes="estimated renal function by the mandated equation",
            catches="Cockcroft-Gault used where the protocol names CKD-EPI"),
        "contraindication": Template(
            "contraindication", BOUND,
            describes="whether anything in the record forbids this",
            catches="a safe-looking dose for a patient who must not have it"),
        "route": Template(
            "route", TABLE,
            describes="the route of administration the formulary permits",
            catches="an oral dose given an intravenous route"),
        "source_cited": Template(
            "source_cited", CITED,
            describes="the formulary or protocol the answer read",
            catches="a plausible dose with nothing behind it"),
    },
)
