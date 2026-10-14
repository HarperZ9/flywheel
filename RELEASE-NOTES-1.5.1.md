# Flywheel 1.5.1

Flywheel now shows you how it works, and each release renders that from its own
files. This release adds a captioned walkthrough video, a short explainer film
and an animated explainer page. The Python package changes only in its version
number.

## Try it

```
pip install -U flywheel-verify
```

On Windows, install `Flywheel-Setup-1.5.1-x64.exe` from this release.
Everything in 1.5.0 is in it; see `RELEASE-NOTES-1.5.0.md`.

## Watch it check an answer

This release carries two videos, 960 x 540 with captions burned in:

- `first-check-540p.mp4`: the Form 1040 example in
  `examples/output-validation`, run three times from a source checkout. The
  answer as filed fails against the tax table (exit 1). The answer that took
  its tax from the table passes (exit 0). The same correct answer with no
  command authority granted is unverifiable, not passed (exit 3).
- `which-source-540p.mp4`: why the filed answer fails. The rate schedule gives
  $4,165.50 at $36,700 of taxable income. The tax table's $50 row uses its
  midpoint and gives $4,169, and the contract names the table as the authority.

Every number on screen is read from this release's files when the video is
rendered: the answers, the authority the contract names, the brackets, the
table's row width, the checker's value, and each run's verdict and exit code.
The scene draws nothing if its own table disagrees with the checker. The
`*-media-v1.5.1.zip` files hold each scene's interactive page, captions and
the facts it read. (#377)

To render them yourself, raw-native's media tool reads `docs/media/media.json`.
In CI the render runs on a hosted runner with a software GPU adapter, so no GPU
is needed.

## Explainer and README

- An animated explainer, `docs/explainer/index.html`, served at
  harperz9.github.io/repo-explainers/flywheel.html. It steps through the run
  lifecycle, the shell capability check on seven real commands, a sealed
  `flywheel gate` result and its recheck, four edits to the envelope with the
  verdict each one gets, and the stage receipt chain. Every value came from
  running the repository at 1ec701d. (#375)
- The README gains a Watch section with the concept film "Re-derive it. Don't
  take it on trust." and a Walkthrough section: install, first run and the main
  feature, with real commands and output. (#376)

## Monitor rule pack

The pre-action monitor's rule pack is unchanged from 1.5.0, so a pinned
`expected_rules_digest` stays valid. `flywheel monitor owner` prints it as
`installed_rules_digest`:

```
a76b7e8995c91861e92ce2198cd62d722deede9fb8307463c68b8aa5d5cdf8c4
```

## Limits

- The videos have captions and no narration.
- The videos are rendered after the release is published, so they appear on the
  release page some minutes after the installer and the wheel.
- The explainer page cites its outputs from flywheel-verify 1.5.0. Nothing it
  shows changed in 1.5.1.
