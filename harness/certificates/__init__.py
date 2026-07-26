"""certificates -- checkers that read data and never run it.

A construction certificate is a data structure: a witness graph, a codebook, a
tensor decomposition. Validating one is arithmetic over that structure, so
nothing here compiles, imports, execs, or spawns. That is what makes shipping a
verifier to a stranger safe rather than an invitation to run arbitrary code.
"""
from .base import (  # noqa: F401
    CertificateOracle, Coverage, CertificateError, OutOfScope,
    parse_certificate,
)

__all__ = ["CertificateOracle", "Coverage", "CertificateError",
           "OutOfScope", "parse_certificate"]
