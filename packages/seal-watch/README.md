# seal-watch

Seal-watch clones two sealed evidence repos fresh every day and runs each repo's own
verifier on them. A sealed repo pins every file to a SHA-256 digest, and its verifier
refuses to pass if anything outside that list appears. Adding a CI workflow inside such
a repo would itself break the seal. So the check runs here, outside the repos it checks.

| Repo | Verifier | Manifest |
|:--|:--|:--|
| [crewai-kickoff-replay-receipt](https://github.com/HarperZ9/crewai-kickoff-replay-receipt) | `verify_public.py` | `SHA256SUMS` |
| [vllm-ci-forum-receipt](https://github.com/HarperZ9/vllm-ci-forum-receipt) | `verify_publication.py` | `SHA256SUMS.txt` |

## What each run checks

The workflow runs daily at 06:17 UTC, on every push to `main`, and on demand.

1. **Three checkout legs per repo.** Ubuntu, Windows with `core.autocrlf=false`, and
   Windows with `core.autocrlf=true`, the Git for Windows default. Each leg clones the
   default branch with that setting.
2. **The repo's own verifier**, run unchanged from the fresh clone.
3. **A plain `sha256sum --strict -c`** of the repo's manifest, so the result does not
   rest on the repo's own code alone.
4. **A recount** of how many manifest digests match the bytes on disk. The recount
   strips a trailing carriage return from manifest lines, so it still gives a count
   when Git has rewritten the manifest itself.
5. **A self-test** on Ubuntu and Windows. It clones each repo, checks that the
   untouched clone passes, flips one bit in one sealed file, and requires both the
   verifier and `sha256sum` to fail. If the watcher cannot catch a one-bit change, the
   run goes red.

The `report` job prints one table with every repo, leg and result in the run summary.
Each leg also uploads its JSON results.

## Known finding

**crewai-kickoff-replay-receipt fails on Windows with `core.autocrlf=true`.** The repo
has no `.gitattributes` pin, so Git rewrites LF to CRLF on checkout. 33 of 38 sealed
digests then differ from the manifest, and the verifier stops at
`canonical execution hash drift`. The stored blobs match their digests: the Ubuntu leg
and the `autocrlf=false` leg pass. A reader on a default Git for Windows install sees a
failed seal for a line-ending reason.

That leg is listed in `targets.json` as a known failure. It still runs and still shows
its counts. It passes only while the failure reproduces exactly as recorded. If the
sealed repo gains a pin and the leg starts passing, the watcher goes red so the record
gets updated.

The fix belongs in the sealed repo: a `.gitattributes` pin and a recorded reseal. That
change needs a decision from the repo's author, so this repo watches and does not fix.

## Run it locally

Python 3.10 or newer, Git, and `sha256sum` on `PATH`. On Windows, Git Bash provides
`sha256sum`. No packages to install.

```sh
python watch.py check --leg local --autocrlf false
python watch.py check --leg local-crlf --autocrlf true
python watch.py tamper --leg local
python watch.py report results
```

Add `--only HarperZ9/vllm-ci-forum-receipt` to check one repo. Exit status is 0 when
every result matches `targets.json`.

## Limits

- A green run means the default branch of each repo matched its own manifest at clone
  time. It does not prove that the evidence inside the bundle is correct, and it does
  not check tags, releases or older commits.
- The verifiers are the sealed repos' own code. A verifier that accepted bad input
  would pass here too. The `sha256sum` check guards the digests only.
- The self-test proves the watcher catches a one-bit change to one named file. It does
  not cover a tampered manifest that was rewritten to match.
- The watcher's result lives on this repo's Actions page, not on the sealed repos'
  commit status.
- The schedule depends on GitHub Actions. GitHub pauses scheduled workflows after 60
  days without repository activity.

## Licence

Text: CC BY 4.0. Code: MIT.

The prose in this repo is licensed CC BY 4.0, terms in [`LICENSE-TEXT`](LICENSE-TEXT).
The code is under the MIT terms in [`LICENSE`](LICENSE).
