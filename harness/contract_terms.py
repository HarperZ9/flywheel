"""contract_terms.py -- the vocabulary an output contract is written in.

Its own module because several files need these names and none of them should
have to import a checker to read a constant.
"""
from __future__ import annotations

SCHEMA = "flywheel.output-contract-report/v1"

# What kind of thing decides a field.
TABLE = "TABLE"            # a lookup that supersedes any formula
RECOMPUTE = "RECOMPUTE"    # an independently written second derivation
CITED = "CITED"            # the answer only has to say where it looked
UNIT = "UNIT"              # the source dictates the unit the value is in
BOUND = "BOUND"            # the source decides whether the value is permitted
AUTHORITIES = (TABLE, RECOMPUTE, CITED, UNIT, BOUND)

# How much a field's failure matters to whether the answer may leave the
# building. This never softens a verdict. It decides what a non-PASS blocks,
# because an unchecked dose and an unchecked footnote are the same verdict and
# not the same risk.
ADVISORY = "advisory"
STANDARD = "standard"
CRITICAL = "critical"
CRITICALITIES = (ADVISORY, STANDARD, CRITICAL)

# Why a field landed where it did. `UnverifiableReason` says why an oracle
# could not run. These say what the answer did.
AGREES = "AGREES"
DISAGREES = "DISAGREES"
UNCITED = "UNCITED"
FIELD_ABSENT = "FIELD_ABSENT"
OUT_OF_RANGE = "OUT_OF_RANGE"
AUTHORITY_UNAVAILABLE = "AUTHORITY_UNAVAILABLE"
METHOD_MISMATCH = "METHOD_MISMATCH"
METHOD_UNSTATED = "METHOD_UNSTATED"
UNIT_MISMATCH = "UNIT_MISMATCH"
UNIT_UNSTATED = "UNIT_UNSTATED"
OUT_OF_BOUND = "OUT_OF_BOUND"

# What may happen to the answer now.
RELEASE = "RELEASE"
RELEASE_WITH_CAVEAT = "RELEASE_WITH_CAVEAT"
HOLD = "HOLD"
