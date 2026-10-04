"""Helpers copied byte for byte from their canonical shared source.

Never edit a file here: VENDORED.sha256 at the repository root records each
copy's SHA-256, and tests/test_vendored.py fails when the bytes drift. Flywheel
code reaches safe_spawn through harness/safe_program.py, never directly.
superstack.py is the superstack contract v0.1.0 (receipts with an identity and a
tolerance verdict); the raw lane's receipts are built and checked with it.
"""
