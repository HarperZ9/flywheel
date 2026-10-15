# Flywheel 1.9.0

Flywheel now installs with Homebrew and Scoop, and it can check itself. `flywheel
behavior-check A B` replays scripted sessions on two builds and says whether
anything a user or the model would see changed, naming the first event that
differs. `flywheel report scope` lists every call in your saved sessions that
reached past what was allowed. Each turn of `flywheel code` records one hash of
the harness settings it ran under, so two runs with equal hashes ran the same
harness. The docs site gains configuration, troubleshooting, and versions and
compatibility pages.

## Behaviour changes to check before you upgrade

- **`-p` JSON results have a new field**, `harness_config_sha256`. Nothing was
  removed or renamed.
- **The session ledger has a new entry kind**, `harness_config`, written when
  the settings of a turn differ from the last ones recorded. Sessions saved by
  1.6.0 to 1.8.0 still load, verify and resume; a test keeps a 1.6.0 session
  for that.

## Install

- Homebrew: `brew tap HarperZ9/flywheel https://github.com/HarperZ9/flywheel`,
  then `brew install flywheel`. Scoop: `scoop bucket add flywheel
  https://github.com/HarperZ9/flywheel`, then `scoop install flywheel`. Both
  install from PyPI files pinned by SHA-256, and CI installs each on macOS and
  Windows. (#409)

## Checks and reports

- `flywheel behavior-check A B` compares the model requests, tool events,
  final files, exit code and ledger kinds of 13 scripted sessions. On a corpus
  written before it ran, it reported 20 of 20 planted behavior changes as
  DRIFT and 0 of 50 unchanged pairs. It sees only what its scenarios exercise.
  (#415)
- `flywheel report scope [--since DATE]` reads saved sessions and lists calls
  refused by plan mode, a deny rule or a hook, declined by you, outside a
  subagent's tools, stopped by the denylist or monitor, aimed outside the
  project, or repeated after a refusal, each with its ledger entry. (#413)
- A harness-config hash on every turn: the system prompt as sent, mode, rules,
  hooks, budgets, sampling settings, the model that answered, the test command
  and the version. (#412)
- An offline recheck of a swarm's sealed fan-in receipt, measured at 8, 64 and
  512 children (under 10 ms from file at each size). The cap stays at 8 until
  children run under a concurrency limit. (#411)
- A footprint and startup suite: on 1.8.0, 10.4 MB installed, 0.29 s warm and
  0.40 s cold to the `flywheel>` prompt, 30 MB at the prompt, on one Windows
  desktop. A gated A/B runner accepts a startup change only when its interval
  shows a gain and no neighbor metric regresses. (#414, #416)

## Docs

- Configuration (every file and environment variable), troubleshooting (one
  section per real failure message), and versions and compatibility (what
  counts as breaking, and that saved records stay checkable). (#408)

## License

Flywheel is licensed under FSL-1.1-MIT; this release converts to MIT two years
after its publication date. What that allows is on the licensing page,
[docs/LICENSING.md](docs/LICENSING.md).

## Monitor rule pack

The pre-action monitor's rule pack is unchanged from 1.8.0, so a pinned
`expected_rules_digest` stays valid. `flywheel monitor owner` prints it as
`installed_rules_digest`:

```
a76b7e8995c91861e92ce2198cd62d722deede9fb8307463c68b8aa5d5cdf8c4
```

## Limits

- Session features and the new checks are tested with a scripted model. No
  hosted model was called in this release's checks. The behavior-check corpus
  ran on Windows only.
- The Homebrew and Scoop files pin 1.8.0 until the follow-up that points them
  at 1.9.0 on PyPI lands; that step needs the digests PyPI publishes.
- The desktop app ships for Windows only. No WinGet package yet.
