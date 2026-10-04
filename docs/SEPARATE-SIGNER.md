<!-- writing-profile: readme -->
# Separate-identity record signer

The pre-action monitor writes a sealed, chained record before every tool call.
Without a signer, those seals are unkeyed sha256 written by code running as the
agent's own OS user, so anyone who can write the store can rewrite it and
recompute every seal. The record signer moves the pen out of the agent's reach.

## What it does

- Runs as its own OS user on Linux, or its own local account on Windows.
- Holds an Ed25519 key in a home directory the agent's user cannot read.
- Answers on a local Unix socket or named pipe with four operations:
  `hello`, `sign_record`, `head` and `check_policy`. It signs nothing else.
  `check_policy` runs the shipped rule pack on one call with the owner's
  context and signs the verdict; ACTION-AUTHORITY.md covers its use.
- Signs each record's sequence number, previous seal and seal once. A request
  that would re-sign, skip or re-point a sequence number is refused, so signed
  history cannot be rewritten through the signer.
- Reads the caller's identity from the kernel (`SO_PEERCRED` on Linux,
  `LOCAL_PEERCRED` on macOS, the pipe client token on Windows) and writes it
  into every signed statement as `isolation`: `separate-identity`,
  `same-identity` or `unattested`.
- Keeps the last signed record per store and returns it as a signed `head`, so
  a verifier can catch a store truncated after signing.
- Logs each store's head in two public logs it does not run, Sigstore Rekor and
  OpenTimestamps, every 15 minutes when the head has moved. Only hashes, a
  signature and the public key leave the machine. A history rewritten later,
  even by someone holding the key, fails against those heads. See
  [Public anchors](#public-anchors).

## Set it up

Install flywheel with a signing backend and the anchor extra into a Python the
signer account can read: `pip install "flywheel-verify[signing,anchor]"`.

**Linux (systemd).** As root:

```
sudo scripts/signer/setup_linux.sh /opt/flywheel/venv/bin/python
```

This creates the `flywheel-signer` system user, `/var/lib/flywheel-signer`
(mode 0700) for the key and journal, the socket at
`/run/flywheel-signer/signer.sock` in a 0755 directory, and a hardened systemd
unit. It also creates `/var/lib/flywheel-signer-anchors` (mode 0755) and the
`flywheel-signer-anchor.timer`, which runs the anchor job every 15 minutes.
Set `ANCHOR_EVERY=30min` before the command to change the period, or pass
`--no-anchor` to skip it. It prints the variables below.

**Windows.** In an elevated PowerShell:

```
.\scripts\signer\setup_windows.ps1 -Python "C:\Program Files\Python313\python.exe"
```

This creates a standard local account `flywheel-signer`, the home
`C:\ProgramData\FlywheelSigner` with an ACL for that account and SYSTEM only,
and a scheduled task that starts the signer at boot under that account on the
pipe `\\.\pipe\flywheel-signer`. The pipe's DACL lets authenticated users ask
for attestations and nothing more. A second task, `FlywheelSignerAnchor`, runs
the anchor job every 15 minutes (`-AnchorEveryMinutes`) and writes receipts to
`C:\ProgramData\FlywheelSignerAnchors`, which every user may read and only the
signer account may write. `-NoAnchor` skips both. The account password is
random and is never shown.

**Then, for the agent.** Set these in the environment the agent's hook runs in:

```
FLYWHEEL_SIGNER=<socket path or pipe name>
FLYWHEEL_SIGNER_PUBKEY=<public key hex printed by setup>
FLYWHEEL_SIGNER_ANCHORS=<anchors directory printed by setup>
```

The third variable is for the verifier, so set it where you run
`flywheel monitor verify` too.

With `FLYWHEEL_SIGNER` set, every record carries an attestation. If the signer
cannot be reached or refuses, the record is not written and the hook fails
closed: the call does not run. With the public key set, an attestation from any
other key is refused before the record is written, so a process squatting on
the address gets nothing accepted.

Start a fresh monitor home when you turn the signer on. Records written before
it have no attestation, and the verifier reports them as `UNSIGNED_RECORD`.

## Verify

```
flywheel monitor verify <home> --trust-root <public key hex>
flywheel monitor verify <home> --trust-root <hex> --signer-head head.json
flywheel monitor verify <home> --trust-root <hex> --anchors <dir> --anchors-online
python -m harness.signer head --address <address> --store <home real path> > head.json
```

| Verdict | Meaning | Exit |
|---|---|---|
| `MATCH` | Seals, links and re-derivation hold, and every record carries a valid attestation from the pinned key for this store | 0 |
| `UNANCHORED` | Internally consistent, but no trust root was pinned. Never a pass | 3 |
| `DRIFT` | Something fails; `findings` names it | 1 |
| `UNVERIFIABLE` | Nothing could be re-derived | 1 |

Findings the trust root adds: `UNSIGNED_RECORD`, `ATTESTATION_INVALID`,
`ATTESTATION_DOES_NOT_MATCH_RECORD`, and with a head, `TRUNCATED_AFTER_SIGNING`
and `SIGNER_HEAD_SEAL_DIFFERS`. The report lists `signer_isolation` for the
records, and warns when any record was signed by a signer sharing the agent's
identity. Without `--signer-head`, `truncation_checked` is false: a store cut
short after signing still reads `MATCH`.

With `--anchors` (or `FLYWHEEL_SIGNER_ANCHORS`), the report gains
`public_anchor`, and three more findings can turn the verdict to `DRIFT`:
`ANCHORED_HEAD_DISAGREES`, `STORE_SHORTER_THAN_ANCHORED_HEAD` and
`ANCHOR_RECEIPT_INVALID`. With `--anchors-online`, a Rekor entry under the
signer's key that has no receipt adds `ANCHORED_HEAD_WITHOUT_RECEIPT`.

| `public_anchor.status` | Meaning |
|---|---|
| `ANCHORED` | Every record is at or before the newest valid public anchor |
| `PARTIAL` | `unanchored_records` came after it. Reported, never a pass for anchoring |
| `NONE` | No receipt verifies for this store |
| `NOT_CHECKED` | No anchors directory or no trust root was given |

`MATCH` with `PARTIAL` still exits 0, because the signatures hold. Add
`--require-public-anchor` to exit 3 unless the status is `ANCHORED`.

## Fallback modes, labeled

- **No signer** (`FLYWHEEL_SIGNER` unset). Records are sealed and unsigned, as
  before. The verifier says `UNANCHORED`.
- **Same-identity signer.** Run `python -m harness.signer serve` as your own
  user, for example on a machine where you cannot create an account. Every
  attestation says `same-identity`, and the verifier warns that the agent's
  user could read the key and forge those records. This still stops a
  careless rewrite. It does not stop a deliberate one.
- **macOS** has no shipped service setup. The signer runs and reads
  `LOCAL_PEERCRED`; that path is exercised by CI's macOS legs only through the
  same-user tests.

## Why one signature per record

The alternative was a signed rolling head every N records. It saves N - 1
signatures, and it leaves the newest records, up to N - 1 of them, covered only
by unkeyed seals: exactly the window in which an agent would rewrite what it
just did. Per-record signing closes that window, and its cost is small next to
the hook that pays it. Measured on one Windows 11 machine (Python 3.12, 200
calls each, same-user signer):

| Step | Median |
|---|---|
| Round trip with no signature (`hello`) | 0.05 ms |
| `sign_record`, including the journal's fsync | 10.3 ms (p95 14.3 ms) |
| Starting the hook's Python process and importing the hook | 208 ms |

Nearly all of the signing cost is the journal fsync, which is what makes "signed
once" survive a crash. These numbers come from one machine and one run. Linux
numbers are not measured here.

## Recovery: a signed record the store never wrote

If the hook is killed after the signer signs seq N and before the store writes
it, every later append conflicts and the hook fails closed. Run, as the signer
identity:

```
python -m harness.signer rewind --home <signer home> --store <store real path>
```

This forgets the last signed record of that store, one step only. The rewind is
kept in the journal and appears in every later signed head as `rewinds`, so it
is never silent. A rewind is an owner power: whoever holds the signer
identity can use it to replace the newest record.

## What the signer does not protect against

The signer's guarantee rests on the operating system's identity boundary: a
separate OS user on Linux, a separate local account on Windows. It also rests
on the host kernel and hypervisor that enforce that boundary. When those fail,
the guarantee fails with them.

- **A compromised host.** An attacker with root on Linux, or SYSTEM on Windows,
  can read the signer's key or have it sign arbitrary records. So can an
  attacker who escapes from a virtual machine into the host that runs it.
  Public reports in 2026 described guest-to-host escapes in KVM, so this class
  of event happens in practice. Records signed after such a compromise prove
  nothing, and the verifier cannot tell them from honest ones. An attacker who
  holds the key can also sign a replacement history, so earlier records are
  only as strong as what was anchored off the host.
- **What still holds.** A head anchored in a public log the attacker does not
  run, Sigstore Rekor or OpenTimestamps, still bounds what had been published
  by the anchor's time. A forged history that disagrees with an anchored head
  fails against it, and the verifier reports `ANCHORED_HEAD_DISAGREES`. A
  signer installed with the setup scripts anchors its heads every 15 minutes,
  so this protection is in effect by default. It covers records up to the last
  anchor only. Records after it stay unprotected until the next run, so the
  anchoring period is the exposure window. An attacker who takes the host can
  also stop the anchor job, and every later record then stays unanchored; the
  verifier counts them and shows the last anchor's time. See
  [Public anchors](#public-anchors).
- **Direction, not built.** Keep the key off the host's reach: a TPM-bound key
  the host can use but not export, or an external device that holds the key, a
  monotonic counter and the hash chain. A host compromise would then not yield
  the key. A compromised host could still submit false records while it holds
  control, and a device that keeps its own counter and chain could refuse to
  rewrite the records it signed before. None of this ships today.

## Public anchors

The anchor job runs as the signer identity:

```
python -m harness.signer anchor --home <signer home> --out <anchors dir>
```

For every store in the journal whose head moved at least `--min-new` records
(default 1) since its last anchor, it signs a head, then:

1. logs the head's SHA-512 and an Ed25519ph signature by the signer's own key
   in Sigstore Rekor, and checks the entry Rekor returns before keeping it;
2. submits the head's SHA-256, salted with a random nonce, to OpenTimestamps
   calendars. The proof starts pending and the next run upgrades it once
   Bitcoin confirms;
3. writes a receipt to `<anchors dir>/<store key>/`. The store key is a hash of
   the store's path, so no path appears in a directory name.

A failed Rekor upload writes no receipt and exits 1. A failed calendar keeps
the Rekor receipt and records the failure. `--dry-run` reports what would be
anchored and sends nothing.

The verifier counts a receipt only when its head verifies under the pinned
trust root and its Rekor entry verifies offline under Rekor's pinned key: the
entry body, the signed entry timestamp, the inclusion proof and the
checkpoint. The trust root is the same key that signed the Rekor entry, so a
receipt written by anyone else does not count. Each valid anchored head must
then match the store's seal at its sequence number.

Limits:

- **The exposure window.** Records after the last anchor are protected by the
  key alone, which a host compromise defeats. With the default timer that is
  up to 15 minutes of records, plus however long the job fails or is stopped.
- **Receipts live on the host.** An attacker with the host can delete them.
  Offline, the verifier then reports `NONE`, which is not a pass but is not a
  finding either. `--anchors-online` lists every Rekor entry under the
  signer's key and fails on one with no receipt. Keep a copy of the anchors
  directory off the host as well.
- **What becomes public.** Rekor is public and permanent. Each entry shows the
  signer's public key, a hash and a time, so the log shows when and how often
  this signer's heads moved. It shows nothing about what the records say.
  `--no-anchor` or `-NoAnchor` turns anchoring off for a machine where that
  timing should not be public.
- **OpenTimestamps lags.** A pending proof bounds nothing until Bitcoin
  confirms it, usually within hours. The report shows `pending` until then.
- **A rewind after anchoring shows.** If the owner rewinds a record that was
  already anchored, the store no longer matches that head and the verifier
  reports `ANCHORED_HEAD_DISAGREES`. That is intended: an anchored record is
  never silently replaced.
- **Network.** The anchor job needs outbound HTTPS to Rekor and the calendars.
  The signing service itself stays local and makes no network call.

## What this does not prove

- **Root defeats it.** A root user on Linux, or an administrator on Windows who
  takes ownership of the signer's home, can read the key and sign anything. The
  split holds only while the agent runs without those rights. Do not run the
  agent elevated. The section above covers a compromised host.
- **The signer attests what it was sent.** The hook builds each record on the
  agent's side. A signature shows the record was submitted in that order and
  not changed afterwards. It does not show the record is true, that the tool
  result was real, or that the monitor judged well.
- **Skipped hooks leave no record to sign.** A call the hook never saw is not
  in the store. The transcript witness (W1) is the check for that, and it
  still runs as the agent's user.
- **The head witness is on the same machine, up to the last anchor.** The
  signer's journal is out of the agent's reach, but not off the host. A host
  compromise takes both. The public anchors are the off-machine copy of the
  heads, and they lag the journal by up to one anchoring period.
- **Clock.** `signed_at` is the signer host's clock.
- **The Windows path is unit-tested as one user only.** CI runs the two-user
  test on Linux. The Windows setup script was parse-checked; it has not been
  run end to end under a second account in CI.
- **Timing and denial of service.** A caller can hold the Windows pipe's
  single instance open and stall other callers; the result is the agent's own
  calls failing closed.
