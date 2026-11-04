"""studyrun: the preregister, run, control, score and ledger stage as one reusable command.

Plain Python, standard library only in the stage itself. Analyses and controls are named units
("path/to/file.py:function") that the spec points at; the stage never knows what they compute.
See docs/STUDYRUN.md for the design, the unit contract and the commands.
"""
SPEC_SCHEMA = "studyrun.spec/1"
SPEC_SCHEMA_V2 = "studyrun.spec/2"  # same shape; the lock also requires the 2026-11-02 upgrade steps
LOCK_SCHEMA = "studyrun.lock/1"
MANIFEST_SCHEMA = "studyrun.manifest/1"
