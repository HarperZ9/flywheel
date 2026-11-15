# Operator smoke: a real course run (operator-gated)

This is run **by the operator**, against a course you are genuinely taking, in the Telos
automation Chrome profile where you are signed in. It exercises the whole loop on a live LMS:
logistics automated, **you** do the graded steps, everything witnessed, receipt emitted.

## Prerequisites
1. Chrome running with the remote-debug port on the Telos automation profile (native-control's
   `ensureChrome`), and **you signed into the LMS** in that profile.
2. `LEARN_NATIVE_CONTROL` set to the absolute path of the native-control folder. There is no
   default: without it, or with a relative path, a `--native` run stops at once with a setup
   message and imports nothing.

## 1. Write a workflow for the course
Tag every graded element `assess` — the engine will halt there for you. Example
(`course.json`), selectors are per-platform (fill them from the real page):

```json
{
  "adapter": "generic",
  "course": "<course name>",
  "steps": [
    { "kind": "navigate", "target": "<course url>" },
    { "kind": "waitFor", "target": "<a selector that means the page loaded>" },
    { "kind": "click", "target": "<mark-module-complete / next button>" },
    { "kind": "capture", "capture": "dom" },
    { "kind": "assess", "label": "Quiz 1" },
    { "kind": "complete" }
  ]
}
```

## 2. Run it against the real browser
```
node src/cli.mjs run course.json --id smoke1 --native --match "<url fragment of your LMS tab>"
```
Expected: it advances the logistics steps and **halts at `assess` ("Quiz 1")**. It will not
touch the quiz.

## 3. Do the graded step yourself, then resume
Complete the quiz in the browser. Then record that you did it and continue:
```
node src/cli.mjs resume smoke1 --native --match "<url fragment>" --attest "completed Quiz 1 myself"
```
Expected: `completed` (it captures the certificate on the `complete` step).

## 4. Verify + receipt
```
node src/cli.mjs verify smoke1      # -> chain ok
node src/cli.mjs receipt smoke1     # -> runs/smoke1.receipt.json + .md
```
The receipt shows the split: automated-logistics steps vs. the graded step **you** performed,
with the captured certificate. That is the credential-provenance record.

## What this never does
No step answers a quiz/exam. `assess` steps always halt. Sensitive fills (credentials, payment
details, CAPTCHA) halt for you, and so do steps flagged `cost` unless you pass `--allow-cost`.
Account creation is not a step kind: do it yourself before the run. Submitting a graded answer is
not a capability of this tool.
