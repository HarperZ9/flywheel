#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
"""Back-compat shim. The EMET Python reference now lives in the emet/ package;
this keeps `python membrane.py ...` and `python conformance/run.py membrane.py`
working byte-for-byte. The real implementation is emet/membrane.py (which is the
selftest artifact-of-record, hashed with its sibling core modules)."""
from emet.membrane import main

if __name__ == "__main__":
    main()
