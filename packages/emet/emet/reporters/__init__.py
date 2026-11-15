# SPDX-License-Identifier: AGPL-3.0-only
"""emet.reporters - optional, OUT-OF-CORE reporters that ship in the wheel.

This subpackage is deliberately NOT part of the minimal Trusted Computing Base
(SPEC section 10). The minimal-TCB guarantee, the zero-dependency posture, and
the selftest artifact-of-record (SPEC s.14, membrane.CORE_SRC) all cover the
NAMED CORE only - membrane, organs, monitor, corpus, verdict, report. A reporter
here is distribution-convenience glue: it emits DATA, never signs, enforces,
uploads, or actuates, and it MUST NOT be imported by the core.

Importing `emet.reporters` (or this package) has NO side effects and pulls in NO
third-party dependency. Each reporter imports its heavy optional dependency
(e.g. deepeval) LAZILY, inside the function that needs it, so `import emet` and
the byte-hash core stay usable with nothing but the standard library installed.
"""
