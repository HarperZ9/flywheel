# EMET examples

A runnable demo that exercises the real EMET witness surface end-to-end.

> Best-effort demo - not runtime-verified by author. It uses only real
> `membrane.py` commands and the public marker corpus, and runs in a scratch
> directory so it writes no state into the repo.

## Files

- `sample-prompt.txt` - an ordinary note that embeds a few public in-band
  authority-marker signatures from `conformance/markers.corpus` (no secrets; the
  markers are *known signatures*, which is why they live in the open). This is
  exactly the kind of self-vouching content `refuse` exists to neutralize.
- `demo.sh` - drives `selftest`, `anchor` + `verify` (MATCH, then DRIFT after a
  one-byte change), `coherence`, `refuse`, `corroborate`, and `audit`.

## Run

```sh
sh examples/demo.sh
```

Override the interpreter if needed:

```sh
PYTHON=python3 sh examples/demo.sh
```

## What to expect

- `selftest` prints the tool's own SHA-256 and declines authority.
- `verify` prints `MATCH` (exit 0), then `DRIFT` (exit 2) after the file is
  mutated by one byte.
- `coherence` prints `COHERENT` for a faithful view.
- `refuse` reports the in-band authority claims by offset (exit 3) and writes a
  neutralized `source.txt.refused` copy with each marker replaced by
  `[REFUSED-IN-BAND-AUTHORITY]`.
- `corroborate` shows the read paths agreeing (`CORROBORATED`); `cat_subproc` and
  `git_read` are environment-dependent.
- `audit` recomputes the tamper-evident log chain and reports `chain=INTACT`.

Exact hashes depend only on the input bytes, so they re-derive identically on any
machine for the same `sample-prompt.txt`. See [../USAGE.md](../USAGE.md) for the
full command reference and per-command expected output.
