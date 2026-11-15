# Articulate documentation

Articulate checks prose on your computer. It flags writing patterns common in weak prose and in model output, scores how densely a passage uses them, and can rewrite a draft with a model you choose. The checker runs on the Python standard library with no network call.

```bash
python -m pip install articulate-writing
articulate check README.md --profile readme --gate
```

## Read in this order

- [Getting started](getting-started.md): install, a first check, a first receipt,
  and an editor squiggle in about five minutes.
- [Walkthrough](walkthrough.md): one document from check to rewrite to a
  committed receipt.
- [Features](features.md): every capability and how to reach it, including
  profiles, modes, genres, the editor, receipts, and the LSP, SARIF and MCP surfaces.
- [CLI reference](cli.md): each command and every flag, with the exit codes.
- [What results mean](boundaries.md): what a check result and a receipt cover.

Articulate finds writing patterns and shows where they are. Use it to improve
writing. Use other evidence to decide who wrote a text. On 183 texts of known
origin it flagged all 84 AI texts and 57 of 75 human texts (76%, 95% interval
65% to 84%), among them 10 of 18 essays by English learners
([`results.json`](../corpus/provenance/results.json)). Teachers: use it to help a
student improve a draft, and use other evidence to judge who wrote an essay.

## More

- [Claude plugin](claude-plugin.md): local checks and host editing in Claude Code.
- [House voice](house-voice.md), [series and your own voice](series-and-voice.md) and [a voice built from intent](voice-intent.md).
- [Dialogue and character voice](dialogue.md): the dialogue profile, voice sheets,
  blind speaker attribution and the CI gate for game and stage scripts.
- [Devices](devices.md): `articulate devices`, thirteen rhetorical devices with
  held-out rates, the spoken view and graded survival in the change report.
- [Structure rules](structure-rules.md): the `chat` profile's paragraph-level
  rules, how a sentence frame is compared, and the measured rates.
- [Calibration](calibration.md): the measured layer after the pinned detector,
  and why the intensifier rule no longer blocks.
- [Campaign signals](campaign.md): `articulate campaign`, promotional-template
  and stock-persona checks with near-duplicate clustering for batches of short
  social texts, and the input and output schema.
