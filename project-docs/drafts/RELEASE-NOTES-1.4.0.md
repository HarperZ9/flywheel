<!-- Draft notes for the release after 1.3.4, reviewed before any tag. Covers #358,
#359 and #361; #361 was open when this was written, so drop its sections if it does not
merge first. At release, move this to RELEASE-NOTES-1.4.0.md at the repo root and add
the matching CHANGELOG section in the release commit. -->

# Flywheel 1.4.0

The pre-action monitor's records can now be signed by a process the agent
cannot impersonate. A small signer runs under its own OS user on Linux or its
own account on Windows, holds a key the agent cannot read, and signs every
record once. The verifier no longer calls a store a pass when nothing outside
the agent vouches for it. Tool-call receipts gain an `authority` field that
says what decided each action, and the verifier re-derives it instead of
trusting it.

## Try it

```
pip install -U "flywheel-verify[signing]"
sudo scripts/signer/setup_linux.sh /path/to/python            # Linux
.\scripts\signer\setup_windows.ps1 -Python "C:\...\python.exe" # Windows, elevated
flywheel monitor verify <monitor home> --trust-root <public key printed by setup>
```

Setup prints the two variables the agent's hook needs, `FLYWHEEL_SIGNER` and
`FLYWHEEL_SIGNER_PUBKEY`. See `docs/SEPARATE-SIGNER.md`.

## Behaviour changes to check before you upgrade

- **`flywheel monitor verify` no longer exits 0 on an unsigned store.** A store
  whose seals and links all hold, verified with no trust root pinned, now
  reports `UNANCHORED` and exits 3. It used to report `MATCH` and exit 0. The
  seals are plain sha256, so anyone who can write the store can rewrite it and
  recompute them; a consistent store with no key behind it shows consistency,
  not that nobody rewrote it. The old result is still in the report as
  `internal_verdict`. A script that treats exit 0 as success fails until you
  pin a key with `--trust-root` or `FLYWHEEL_SIGNER_PUBKEY`, or accepts exit 3.
- **Receipts with no `authority` field verify as FINDING under the new
  authority check.** Every tool-call receipt written before this release has no
  `authority` field, and the agent loops do not fill it yet, so almost every
  receipt today has none. `verify_action` reports those as `FINDING` with
  `NO_AUTHORITY_RECORDED`, never as a pass. The reason is the rule the field
  exists for: an action with nothing recorded as deciding it has no basis
  anyone can check, and calling that a pass would hide the gap. The receipt's
  seal check, `verify_receipt`, is unchanged and still returns `MATCH` for an
  intact receipt; only the new authority check reports the finding.
- **A store from before the signer reads `UNSIGNED_RECORD` once you pin a
  key.** Start a fresh monitor home when you turn the signer on.

## A signer the agent cannot impersonate (#359)

- Runs as its own OS user (Linux, systemd) or its own local account (Windows,
  a scheduled task), with its key and journal in a home the agent's user cannot
  read. It answers on a Unix socket or a named pipe and signs only record
  attestations, store heads and policy verdicts, never bytes a caller chooses.
- Signs each record's sequence number, previous seal and seal once. A request
  to re-sign, skip or re-point a sequence number is refused, so a record it
  signed cannot be replaced through it. A signed head catches a store cut short
  after signing (`TRUNCATED_AFTER_SIGNING`).
- Reads the caller's identity from the operating system (`SO_PEERCRED`,
  `LOCAL_PEERCRED`, the pipe client token) and puts it inside the signed bytes:
  `separate-identity`, `same-identity` or `unattested`. A signer running as the
  agent's own user still works; every record it signs says `same-identity`, and
  the verifier warns that the agent could have read the key.
- Fails closed: if the signer is configured but unreachable, refuses, or answers
  with a key other than the pinned one, the record is not written and the call
  does not run.
- One signature per record rather than a signed head every N records, so the
  newest records are never left under plain hashes. On one Windows 11 machine a
  signature took 10.3 ms median (p95 14.3 ms, 200 calls), almost all of it the
  journal's fsync, against 208 ms to start the hook process. Linux was not
  measured.
- A CI job runs the signer as a real second Linux user and checks that the
  agent's user cannot read the key, list the signer's home, or write its
  journal, and that a rewritten record is caught.

## What decided an action (#361)

Tool-call receipts can carry an `authority` field. Its basis is one of
`intent` (the human's goal, quoted, with date and source), `policy:machine` (a
rule checked outside the agent), `scope` (a role or task boundary),
`policy:self` (a rule only in the agent's own instructions) or `none`.

- `none` is a FINDING and `policy:self` is UNENFORCED. Neither is a pass.
- When scope and policy disagree, the narrower decision wins. The receipt keeps
  both and names the winner, and the event goes to a sealed disagreement log.
- A confirmation counts as `intent` only when it names the thing acted on and
  the fact that matters in the human's own words. A bare "yes" or a restated
  plan counts as `scope` at most.
- `policy:machine` comes from the signer: it runs the shipped rule pack on the
  call with the owner's context file and signs the verdict. The verifier counts
  it only under the pinned key, from a separate-identity signer, for this call,
  with the signed decision. Anything else is re-labelled `policy:self`.

See `docs/ACTION-AUTHORITY.md`.

## The preregistration head is current (#358)

`artifacts/prereg/signed-head.json` had signed the log at one entry while the
log held eight. It now carries the signed head over all eight, the head the
existing OpenTimestamps anchor already covers, and every new entry replaces it.
The original one-entry head is kept byte for byte at `heads/head-0001.json`,
and `FREEZE.json` points there. CI fails if the signed head and the log ever
disagree again. No log entry changed.

## Preregistration heads anchored where the author cannot redo them

`flywheel anchor head` logs a signed head's SHA-512 and an Ed25519ph signature in
Sigstore's Rekor and submits its SHA-256 to OpenTimestamps. Only hashes and the
signature are sent. `flywheel anchor verify` rechecks the Rekor entry offline
against Rekor's pinned key (signed entry timestamp, inclusion proof, signed
checkpoint) and the OpenTimestamps proof against its stored Bitcoin header;
`--online` refetches the entry and proves the log has not rewritten the tree.
The prereg size-8 head is logged at Rekor index 3077414145. See
`docs/features/rekor-anchor.md`.

## Monitor rule pack

The rule pack is unchanged from 1.3.4, so a pinned `expected_rules_digest`
stays valid:

```
a76b7e8995c91861e92ce2198cd62d722deede9fb8307463c68b8aa5d5cdf8c4
```

## What this release does not prove

- A root user, or a Windows administrator who takes ownership of the signer's
  home, can read the key and sign anything. The split holds only while the
  agent runs without those rights.
- The signer attests what the hook sends it. A signature shows a record was
  submitted in order and not changed afterwards, not that it is true. A call
  the hook never saw has no record to sign.
- Signer heads stay on the same machine; no off-machine export ships yet.
- The Windows two-account path is not tested end to end. Its code runs in CI as
  one user, and the setup script has been syntax-checked only.
- The receipt signing key still lives under the agent's user.
- Whether a confirmation is `intent` depends on what the human wrote. The
  restatement threshold is a heuristic, not a measured boundary.
