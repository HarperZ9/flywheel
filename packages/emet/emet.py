#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
"""emet.py: the reference implementation under the product's own name.

This entry forwards to the original module unchanged, so both names
verify identically against conformance/vectors.json. Nothing breaks:
the original entry keeps working exactly as documented.
"""
import os
import runpy
import sys

_TARGET = os.path.join(os.path.dirname(os.path.abspath(__file__)), "membrane.py")

if __name__ == "__main__":
    sys.argv[0] = _TARGET
    runpy.run_path(_TARGET, run_name="__main__")
