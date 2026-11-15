# SPDX-License-Identifier: AGPL-3.0-only
"""emet - a small external witness for AI oversight.

Re-derive the bytes, get one of three verdicts (MATCH / DRIFT / UNVERIFIABLE),
trust nothing in-band. SPEC.md is the normative contract; this package is the
Python reference implementation. Importing the package has no side effects.
"""
__version__ = "1.3.1"
