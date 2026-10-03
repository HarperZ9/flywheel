# G4: held-out rerun of the shipped hard benchmark

PREREG.md and PREREG.sha256 are byte-identical to the frozen copies. The script is
`scripts/run_heldout_rerun.py` in this repository; its SHA-256 is in PREREG.sha256. hard.json is
the primary set (n = 10), hard_v2.json the secondary set (n = 110). The primary interval includes
zero, so no accuracy uplift is claimed.
