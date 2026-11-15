# Changelog

All notable changes to `articulate-writing` are recorded here. The package uses
semantic versioning. This is the package version. The detector ruleset carries its
own `RULESET_SEMVER`, which a receipt records so a replay knows which rules ran.

## Unreleased

### Added

- `articulate code test-diff BASE [HEAD]` reads a change's Python test files
  before and after, without running them, and reports where the tests now check
  less: a check deleted or replaced by a weaker form, a new skip or xfail, a
  widened tolerance or expected exception, a deleted test, a test renamed so it
  no longer collects, and a new check that cannot fail (`assert True`, a value
  compared with itself, a mock-only check). `--before OLD.py --after NEW.py`
  compares one file with no repository. A finding the change explains is shown
  as `declared` or `advisory` and is not counted. The command is report-only:
  it exits 0 whatever it finds and 2 on a usage or git error, and `--json`
  carries `status` for a caller that wants a gate. Python only; test files in
  other languages are listed as unverifiable. The work was written on the
  articulate branch `claude/code-test-diff-analyzer` and had not been merged.

### Fixed

- `articulate audit --reverify --gate` exits 1 when a receipt's source file is
  missing or the receipt names none, and when no receipt was found. Before, a
  missing source was counted and the gate passed, so an audit run from the wrong
  folder re-verified nothing and exited 0; the GitHub Action's `audit-path` step
  passed that way from a repository root. The failure names each receipt and the
  path it looked for. Without `--gate` the audit reports as before.

## 0.19.1

Structure rules for a model's replies. A reply passed `check` with a texture
score of 0 on 2026-11-15, and its reader then read it back as a list of faults.
These rules report what the line checker passed.

Released 2026-11-15. This is the first version on PyPI with these changes.
Version 0.19.0 was tagged an hour earlier and its publish stopped at the
release gate, because its changelog section opened with the date line where
the gate wants a summary. Nothing was uploaded for 0.19.0. A test now holds
that rule before a merge, and the Discover check gates on a release branch.

- New rule pack `structure`, on under the `chat` profile and in the house voice
  notes: `structure-anaphora`, `structure-parallel`, `structure-triad`,
  `structure-pin`, `structure-parataxis`, `structure-pointer` and
  `structure-landing`. A finding spans the whole run of sentences. The HIGH
  findings gate under `chat`. No other profile lists the pack, so `author-voice`
  and `narrative` text raises none of these findings.
- `chat` now resolves to a domain profile that adds the pack to the published
  chat register. The published detector, its rules and its fingerprint are
  unchanged.
- Under `chat` the cadence block adds `longest_opener_run` and
  `repeated_openers_in_a_row`. The published `repetitive_openers` flag is a
  whole-document ratio and stays as it is.
- The MCP `check` and `score` tools take an optional `profile`. With one, they
  also return `gate` and `blocking_count`. With none, the default line rules run
  as before. A model that checks its own reply to a person should pass
  `profile: "chat"`, and the tool descriptions now say so.
- Every MCP `check` and `score` result carries `rules_run`: the profile, the
  rule packs that ran, and whether the structure rules were among them. On the
  day these rules were written a session read "clean" from the default rules as
  permission to send a reply. An unprofiled result now says in `rules_run` that
  the structure rules did not run. No existing field changed its meaning.
- The texture score counts line rules only, and it is the published detector's
  figure, so rule-pack findings do not feed it. A blocked reply with 8 HIGH
  findings printed "texture 0/100" beside the failure. Decision: keep the
  texture score as it is and never show it alone when rule packs found
  something. A check result that ran rule packs carries `pack_findings` (counts
  by tier). The terminal headline reads `rule-pack findings 12, texture 0/100
  (line rules only)`, and the MCP result adds `texture_scope`. Dropping the
  texture figure from a blocked result was the other option. It would have left
  the bare zero in the JSON and in every unblocked result with MEDIUM pack
  findings, so the second named figure is the one that cannot mislead. The
  edit hook and the Stop hook print findings and no texture figure, and a test
  holds that.
- The pin, pointer and landing rules read a list item as a short paragraph. A
  hand-back that closes a bullet ("That one is your call.") is a landing
  sentence. The run rules stay out of lists, and the wrapped lines under a
  list marker are read with their item, where they used to be read as a
  paragraph of fragments.
- `structure-landing/handback` (MEDIUM) reports a hand-back before the end of a
  paragraph. A long sentence that ends within four words of the hand-back
  counts as one. "Their decision was final." no longer matches: the possessive
  form needs "is", "was" or the end of the sentence. A hand-back inside
  quotation marks is a mention and raises nothing.
- A quoted span stays inside the sentence that quotes it: a full stop inside
  quotation marks ends no sentence, and neither does one inside a closing
  bracket when the text runs on in lower case.
- `structure-anaphora/pronoun-run` (MEDIUM): exactly three sentences in a row
  that open on one personal pronoun report and do not gate, and an opener alone
  makes them no triad. This was the largest source of HIGH findings on human
  prose, and none of 52 sampled replies held one. HIGH findings fell from 14.7
  to 5.1 per 1,000 sentences on the human corpus and from 9.6 to 7.6 on four
  books. Four or more in a row still gate.
- `articulate check` prints where a structure finding starts and ends
  (`L1:85-L1:207`) and the first and last words of its span. It used to print
  the start of the line.
- `tests/fixtures/structure/readback/` holds texts a person read and judged,
  with the spans the reader objected to and the rule the reader named. A test
  reports each rule's recall against those marks. The folder's README says how
  to add a case.
- Series review adds `corpus/sentence-template` and `corpus/ritual`: a sentence
  ending or an opening that several documents by one author share. Report only.
  The corpus thresholds changed, so a corpus receipt from an earlier version
  reads Unverifiable.
- [Structure rules](docs/structure-rules.md) gives each rule, its thresholds,
  the measured rates on 52 replies and on human prose, the three worst false
  positives, and which of one author's 23 prose rules have a detector.

## 0.19.0

Tagged on 2026-11-15 and never published to PyPI. The publish workflow stopped
at its first gate, before any build. Every change listed under 0.19.1 was in
this tag.

## 0.18.0

Your own voice now has a profile that keeps it. Literary devices are read by
the work they do, and product copy and personal notes have checks of their own.

- New domain profile `author-voice` for your own first-person writing. No device
  gates. `device-empty` (LOW) reports a device whose sentence carries no image,
  anchor or stance, or whose figure rests on a stock vehicle. Claims are still
  checked against evidence and em-dashes are still reported.
- `articulate.voice_register` measures fifteen register features (imagery,
  forward motion, runs of ideas, observer, first person, questions, reader,
  contrarian, jaded, wonder, defensive, profanity, analogy, symbol,
  confrontation). An edit planned under
  `author-voice`, and `voice apply`, keep the original text when a rewrite
  loses one; `voice apply` takes `accept_register_change` to accept it anyway.
  `articulate voice register DRAFT REWRITE` prints the comparison.
- `articulate devices --function` adds simile, metaphor and motif, and reads
  each device as `carries` or `empty`.
- Built-in intent spec `author-voice`: wants imagery, the observer, forward
  motion, a counter-view, a stance, a turn and a reader question, and sets no
  device limit.
- New domain profile `product-copy`: `claim-without-evidence` (LOW, with the
  document's claim coverage in the label), `lead-author-framed` (MEDIUM) and
  `mission-missing` (LOW). It keeps and freezes the author's own terms.
- `articulate.analogy` reads analogy: `carries` with two or more mapped parts
  or a relation carried across, `empty` for a bare stock comparison. A literal
  comparison with real figures is not a device.
- New domain profile `publication`: the research profile plus claim evidence
  and `analogy-untested` (LOW, advice) for an analogy that carries the argument
  and points at no testable map.
- `claim-without-evidence` also reads a statistic about people ("90% of you",
  "studies show"), and a claim's own number no longer counts as its source.
- New domain profile `note`: a stock opener and a stock closing offer gate;
  office words and length report.
- Domain profiles can carry `gate_promote` and `freeze`; freeze terms enter
  every edit plan made under the profile.
- The edit limit lines in the plugin skill, the plugin README and the hosted
  `edit_submit` description now state their scope plainly.
- The edit hook leaves quoted words out of its style findings. Words inside
  double or curly quotation marks and Markdown block quotes belong to the
  person quoted, so the hook no longer asks the model to fix them, and it says
  how many findings it left out. `ARTICULATE_EDIT_HOOK_QUOTES=check` checks
  them again. The detector itself is unchanged.
- New domain profile `outbound` and rule pack `privacy`, for text about to
  leave your machine. `private-email` (MEDIUM) names an e-mail address and
  `local-path` (MEDIUM) names a Windows drive path, a home folder or a network
  share, code blocks included. `outbound` gates on both. `note`,
  `product-copy` and `publication` report them without gating. Reserved
  example domains and no-reply addresses are left alone.
- The detector, its ruleset and its fingerprint are unchanged. Receipts that
  used a domain profile read `Unverifiable` after this change, because the
  extension fingerprint covers the new packs.

## 0.17.1

Publishes the 0.17.0 changes to PyPI. The 0.17.0 release stopped before
upload because CITATION.cff still named 0.16.0; the citation metadata now
matches the package. No code changed.

## 0.17.0

You can now see the rhetorical devices in a draft, hear the findings read
aloud, and see how much of each property an edit kept. The intensifier rule no
longer blocks learner writing under the default profile.

- `filler-intensifier` no longer blocks under the default profile. It still
  shows on every report, as a LOW finding labelled `report only:`. On the Liang
  et al. (2023) essays it blocked 26 of 91 TOEFL learner texts against 2 of 70
  length-matched US college essay windows. With the change, the TOEFL minus
  college blocked-rate gap on a held-out half goes from +0.24 to 0.00. A profile
  that wants the rule to block names it in `gate_promote`. The decision record
  is `docs/calibration.md`.
- A HIGH or MEDIUM finding inside a quotation attributed to someone else (a
  speech or citation verb beside the quote) moves to LOW with the label prefix
  `quoted:`. Quotation marks around your own paragraph change nothing.
- Both changes live in a new layer, `articulate.calibration` (`calibration/1`),
  after the pinned detector. The ruleset and its fingerprint are unchanged. A
  receipt names the layer when it moved a finding, and receipts made before it
  still verify.
- `articulate devices` reads thirteen rhetorical devices: antithesis,
  tricolon, anaphora, chiasmus, alliteration, assonance, polysyndeton,
  asyndeton, anadiplosis, epizeuxis, isocolon, zeugma and oxymoron. It reports
  where each one is and never gates. Rates on a held-out set written without
  sight of the readers are in `docs/devices.md`.
- `--speak` and `--ssml` on `articulate devices`, and `--speak` on
  `articulate check`, give a script of the findings to read aloud.
- The change report from `--explain` carries `survival`: a clarity value for
  each fact, device, rhythm, sentence order and register, 1 kept, below 1 lost.

- Reports and receipts now name their limit field `scope`, and each scope says
  what the result covers. The field was named `does_not_prove` before. These
  schemas move to version 2: changes, meaning, corpus-report, corpus-receipt,
  desk, interview, titles, restructure, voice-compare, house-receipt,
  process-summary, editor-receipt and the dialogue report. `articulate verify`
  still accepts version 1 corpus receipts, voice comparisons, house receipts and
  process summaries. To read either version in your own code, read `scope` and
  fall back to `does_not_prove`; `articulate.scope.scope_of` does this.
- Tool descriptions say "Runs on your machine". The findings tools say "Use the
  findings to improve writing. Use other evidence to decide who wrote a text."
  The CLI describes Articulate as a tool that finds writing patterns and shows
  where they are.
- `articulate campaign` reads a JSON list of short social texts and reports
  promotional templates in posts, stock-persona slot grammar in bios, and
  clusters of near-duplicate or templated posts with their shared skeleton.
  Each finding names the pattern, its offsets and its cost to a reader. The
  report format is `articulate-campaign-report/1`, with a JSON schema at
  `docs/campaign-schema.json`. Python API: `articulate.campaign.analyze`.
- A labelled synthetic corpus in `corpus/campaign/` with ESL, dialect,
  translated, code-switched and non-English hard negatives, a per-platform
  split, a per-stratum fairness bound and controls that must fail. Run it with
  `python -m articulate.campaign_bench`. No change to the prose checker or its
  ruleset.

## 0.16.0

You can now build a voice from what you want a piece to do, and check a draft
against it. The release also adds the negation-load check.

- `articulate voice intend` builds a voice spec from a goal, an audience, a
  stance and optional reference samples, and prints a plan: open on an anchor,
  name the opposing view, try the other side, ask what if, say what you think,
  turn once, end on a question. Samples leave hashes and device counts, never
  text. `--base zain` starts from the built-in spec made from the author's
  prose rules and his stance for posts.
- `articulate voice check DRAFT --intent SPEC` scores a draft from 0 to 100
  against a spec and lists each miss with its line and a fix. `--min-score`
  sets an exit code for hooks and CI.
- New cross-sentence device checks (`articulate.voice_devices`) find what the
  line checker misses in posts built from one-sentence paragraphs: one-line
  paragraphs, anaphora and epistrophe runs, fragment runs, tricolons, the
  split antithesis ("That's not faith. That's hypocrisy."), aphorism lines,
  a closing maxim, numbered escalation, colon drumrolls, stock reveal phrases
  and hedges.
- `articulate negation` scores each entry by the share of its clauses spent on
  what a thing lacks: "does not", "never", "no server", "not yet", "only",
  "limited to". The copy rule warns at 30% and fails at 50%. The fiction rule
  warns at 45%, fails at 65% and skips character speech. The report also lists
  virtue phrases such as "provenance" and "verifiable". Readers cover Markdown,
  HTML, `.lwd` scripts, JSON film scripts and JavaScript UI strings.

## 0.15.1

A patch release. It is also the first release to use the patch path that 0.14.0
opened.

- The art footer reads "Zain Dana Harper / on PyPI". It had read "A Flywheel
  lane / beta", which is internal language.
- `editor.py` is split into `editor.py`, `editor_text.py` and `editor_cli.py`,
  each under 300 lines. Every name still imports from `articulate.editor`.
- The package keywords no longer list `ai-detection`. Articulate checks style
  and does not detect who wrote a text.

## 0.15.0

The editor now does part of the work the checker points at, and it refuses
rewrites that change meaning.

- `fix --backend none` removes a closed list of openers, such as "Moreover,"
  and "It is crucial to note that". Each edit passes the meaning check on its
  own, and the receipt lists it.
- A model rewrite that reorders a date or adds a HIGH or MEDIUM device, or a
  corrective negation, keeps the original paragraph. The CLI prints the reason.
- When the gate blocks a text, the judge sees the blocking findings. A judge
  result that names none of them reads `quality_status: unreliable`.
- In Markdown, inline and display math between `$` signs is skipped, and a
  sentence-start name counts as a name when the same name appears mid-sentence.
  Receipts record `markdown/2`; `markdown/1` receipts still replay.
- The hero images and the social card carry the current caption.
- MCP `fix` and `polish` return `kept_original_reason` when they hand back the
  original text.
- SARIF output validates against the 2.1.0 schema in the tests, and an absolute
  path goes out as a `file:///` URI.
- The GitHub Action takes inputs through the environment, matches `**/*.md` at
  the repository root, and stops on a pattern that matches nothing. New inputs:
  `gate` fails the build on a blocked file, and `upload-sarif` can skip the
  upload. CI now runs the hook and the action from clean repositories.

## 0.14.0

Bug fixes now ship as patch releases, the command line reports its version, and
the `[mcp]` extra installs a fastmcp that works.

- `articulate --version` and `-V` print the package version. Before, the flag
  failed with exit 2.
- The native release check no longer refuses a version whose patch number is
  above 0. That check stopped the 0.12.1 publish. The tag, ref, clean-tree and
  ruleset checks still apply. `RELEASING.md` describes the process.
- The `[mcp]` extra now reads `fastmcp>=3.2.4,<4`. fastmcp 4 dropped the tool
  annotation hints. A new CI job installs `[mcp]` and `[hosted]` and runs the
  MCP tests and the full suite with them.
- A voice range no longer goes below 0, and a share range stops at 1. A rate
  had read `your range -0.134 to 1.474`.
- The pre-commit hook description and the hero caption source now describe
  named writing devices. They had said "AI and prose tells" and "AI-tell
  detection".
- `scripts/sync_local_install.py` prints the version that the PATH command, the
  Claude Code MCP server and the plugin each run.

The Markdown structure fix below shipped in this release too.


Markdown structure no longer reads as prose. The detector rules and their
fingerprint are unchanged; the fix sits in the check layer in front of them.

- A table delimiter row such as `|---|---|` or `| :--- | ---: |` was reported
  as a HIGH em-dash, which blocked any Markdown file with a table under
  `--gate`. Agents had started rewriting tables as `|-|-|` to quiet it. The row
  is now blanked before the rules run. An em-dash or `---` inside a table cell
  still fires.
- An indented code block, outside a list, and TOML front matter between `+++`
  lines are blanked the same way. YAML front matter and fenced code were
  already skipped.
- A register word inside a run of capitalised words, such as "Transformative"
  in "the Transformative AI Fund", is no longer reported. A heading, a word
  that opens a sentence, and a Title Case line still fire.
- `articulate check`, the per-paragraph view, receipts, the MCP `check` and
  `score` tools, the edit hook, the editor gate and the house notes all use the
  same masks. On 3,000 Markdown files under the workspace the masks removed
  5,123 separator findings, 8 register words in names and 2 findings inside
  indented code, and added none.
- A receipt for text the masks change records `"structure": "markdown/1"`, and
  `verify` replays it with the masks. A receipt without the field replays
  without them, so receipts made by earlier releases still read Match.
- Still open: `---` inside inline `$...$` math, and block quotes, which can be
  a cited source or the author's own callout.

## 0.13.0

Documentation and package metadata only. No rule, threshold or finding changes.

- The README opens with what Articulate checks, who it serves, an install and
  first run, a comparison with Vale, proselint, write-good, LanguageTool,
  Grammarly and Hemingway Editor, and short limits. PyPI shows that text from
  this release on.
- The package summary names the 57 of 75 human-text result beside the style
  claim, and the author entry carries a contact address.
- The v0.12.1 tag carried these changes first. Its publish run stopped at the
  native build, which accepts only release versions that end in `.0`, so
  0.12.1 never reached PyPI and has no release assets.

## 0.12.0

Public descriptions now say what the evidence supports. No rule, threshold or
finding changes. The 0.11.0 release went out before this change merged, so its
PyPI description still read "AI-tell detection".

- On the known-provenance corpus the bench call flags all 84 AI texts and 57 of
  75 human texts (76%, 95% interval 65% to 84%), 10 of 18 essays by English
  learners among them. Articulate measures writing devices, not authorship.
- The README, the package description, the CLI and MCP tool descriptions, the
  GitHub Action, the VS Code extension and the docs no longer present it as
  detecting AI authorship. They call it a style tool, link
  `corpus/provenance/results.json`, and say never to use a finding to accuse a
  person or to judge a student's work.
- `--spans` is described as per-paragraph findings, and the bench prints its
  counts as a regression check, not as recall and specificity.
- The hero image still carries the older tagline in its pixels. It needs a
  re-render through the art pipeline, which keeps receipts for its bytes.
- The package docstring in `articulate/__init__.py` keeps its older first line.
  The release check pins that file's bytes with the v0.5.2 detector closure, so
  it changes with the next reviewed ruleset.

## 0.11.0

Dialogue and character voice checks for game and stage scripts. Detector rules
for prose are unchanged, and no prose finding changes.

- `articulate dialogue FILES_OR_DIRS --voices DIR` reads LWD, `NAME: text` and
  printed-play scripts and reports every spoken line against a dialogue
  profile: antithesis and contrast pairs, epigram shapes (semicolon pivots,
  definitions of abstractions, maxims, "In A ... here ..." comparisons),
  characters stating the theme, closing zingers and abstract-noun density.
  Plain, broken and repetitive speech is left alone.
- Character voice sheets (`articulate-voice-sheet/1`, one JSON file per
  character) hold register, region markers and idioms, a sentence-length
  range, never-words and patterns, keyword knowledge bounds, wants, fears,
  secrets and tics. Each line is checked against its speaker's sheet.
- Blind attribution: a complement naive Bayes classifier, trained on the other
  folds of the script, names the speaker of each held-out line. The report
  gives per-character accuracy with Wilson 95% intervals against chance.
- JSON output, a summary table, a Markdown report (`--markdown`) and a gate for
  CI (`--gate`). The same audit is the `dialogue_check` MCP tool.
- Calibrated on public-domain dialogue by Shaw, Chekhov (Fell and West
  translations), Twain and Dickens, with Wilde as the epigram contrast:
  epigram shapes on 0.1 to 0.5 percent of naturalistic lines and on 1.6
  percent of Wilde's. `scripts/dialogue_calibrate.py` repeats the measurement;
  see `docs/dialogue.md`.

## 0.10.0

The v0.9.1 tag never reached PyPI: the release build accepts only versions
ending in .0, so the same changes ship as 0.10.0.

A measured baseline with known provenance replaces Pangram, and bench
references name their model version. Detector rules are unchanged
(fingerprint `sha256:9f78a7484bb20f84`), and no finding changes.

- `corpus/provenance/` holds 183 documents whose origin is known: 75 human
  texts (public-domain books and speeches, and PERSUADE 2.0 student essays
  kept local), 84 texts from four local models and 24 local-model edits of
  human texts. `manifest.json` hashes every document and records the
  licence, or the model, digest, prompt, seed and date.
- `scripts/provenance_eval.py` measures the bench call against that ground
  truth. On this corpus: recall 84 of 84 (95% interval 0.96 to 1.00),
  false-positive rate 57 of 75 (0.65 to 0.84), precision 0.60 (0.51 to
  0.67) against a base rate of 0.53. The bench call separates AI text from
  human text only a little better than chance here; see
  `corpus/provenance/README.md` for the breakdown and the limits.
- Binoculars and Fast-DetectGPT run locally as comparison detectors
  (`scripts/provenance_detectors.py`), with every score recorded beside its
  text hash, model pair, versions and date. AUROC 0.85 and 0.81.
- Pangram is retired as the baseline. Its records and rescore script stay as
  an optional tool.

- The bench reads `corpus/pangram-records.jsonl`. Each record names the text by
  SHA-256 and carries the model version the result came from and the scan
  date. Records are appended and never rewritten, so a new Pangram model sits
  beside the old results. A corpus without the file falls back to the
  `.pangram` sidecars, now shown as "model unrecorded".
- The two existing sidecar results are kept unchanged and recorded with model
  `unrecorded`, since their version and date were never written down.
- `scripts/pangram_rescore.py` estimates the cost of a rescore with no network
  call and, with a key, scores the corpus under a named model.
  `scripts/pangram_agreement.py` reports agreement, precision, recall and
  AUROC per model version with 95% intervals and lists every disagreement.
  Both are reports. No rule, gate or editor setting is chosen from them.
- `corpus/PANGRAM.md` records the Pangram versions (4 and 4.1), the record
  format and the known limits.

## 0.9.0

The 0.8.0 release build stopped before PyPI, so 0.9.0 is the first PyPI release
after 0.7.0 and carries everything listed under 0.8.0 as well. Detector rules
stay the published v0.5.2 rules (fingerprint `sha256:9f78a7484bb20f84`), and
with no project config and no domain profile, command output is byte-identical
to 0.8.0.

One release line. `main` now carries everything released from `release/0.5.x`
(0.5.1 to 0.8.0), so every later release comes from `main`.

- The writing-process record, disclosure statements and the review desk come
  over from `main`: `articulate process`, `articulate disclose` and
  `articulate desk`. `fix` and `polish` add an assistance entry to a document's
  process log when it has one. These commands add no detector rule and
  change no finding.
- Detector rules stay the published v0.5.2 rules (fingerprint
  `sha256:9f78a7484bb20f84`), so every 0.7.0 and 0.8.0 receipt still verifies.
  The reworked detector, the fairness harness and `check --house-notes` that sat
  on `main` change findings, so they stay out of this line until a reviewed
  ruleset change. Their history stays reachable from `main`.
- `fix`, `polish` and `plan` take `--allow-change KINDS`, and the MCP `fix`,
  `polish` and `edit_plan` tools take `allow_change`, so an edit can update a
  number, link, citation, quote or other named kind of protected content on
  purpose. Each allowed change is listed in `allowed_changes` in the result and
  the editor receipt. The plan binds the list, so a submission cannot widen it.
  Disclosure lines, added first-person sentences, HTML and math can never be
  allowed. Plans that allow nothing keep their old schema and plan IDs.
- `fix`, `polish` and `submit` take `--explain [json|text]`, and the MCP `fix`,
  `polish` and `edit_submit` tools take `explain`, for a change report: each
  changed sentence before and after, the findings it cleared, kept or added,
  the paragraphs the guard kept and why, and each allowed change.
- Five domain profiles add rule packs for one kind of writing:
  `ux-microcopy` (UI string length, case, vague errors and link text),
  `code-review` (condescension, absolutes and requests with no reason),
  `plain-language` (reading grade, long sentences and wordy phrases),
  `controlled-english` (sentence length, one instruction per sentence, idioms,
  phrasal verbs and vague pronouns; no ASD-STE100 conformance is claimed) and
  `rfc-keywords` (`normative-spec` plus RFC 2119 and RFC 8174 keyword checks).
  Choose one with `--profile`, an in-file `writing-profile:` tag, the LSP
  server or an edit plan. The packs run after the detector, so the detector
  rules, every existing profile and every existing receipt are unchanged.
  Receipts under a domain profile record an `extension_fingerprint`, and a
  pack change makes them read Unverifiable. `python -m articulate.bench` also
  runs the new domain regression corpus.
- The hosted MCP service accepts edit plans built under a domain profile.
  It refused them before. A plan whose domain profile was altered is still
  refused.
- A project config file, `.articulate.json`, found by walking up from each
  file (nearest wins). It maps path globs to profiles, adds banned and
  preferred terminology with their own rule ids, allows terms of art, freezes
  terms that every rewrite must keep, and tunes rule-pack options. `check`,
  `score`, `receipt`, `plan`, `judge`, `fix` and `polish` take
  `--config PATH|none`, and `articulate config PATH` shows what applies to a
  file and why. Terminology findings appear in check text, JSON, SARIF,
  per-span verdicts, LSP diagnostics and receipts. Receipts embed the project
  rules with their hash, so they replay anywhere; an edited payload reads
  Unverifiable. A malformed config stops the command with exit 2, the file and
  the reason. With no config file, output is unchanged.
- The Windows x64 native package now carries the house voice spec. The 0.8.0
  release build stopped because the frozen server could not find that file at
  start-up, so 0.8.0 never reached PyPI. The release check now lists all 17
  local tools and runs `house_transform` in the frozen binary.

## 0.8.0

Two voice layers and series review. Articulate ships a house voice for the
model in your client, opt-in and openly a model's voice, and a personal
voice that each user builds from their own writing on their own computer. No
person's voice ships in the package. Detector rules stay the published v0.5.2
rules (fingerprint `sha256:9f78a7484bb20f84`); this release changes no finding,
and every 0.7.0 receipt still verifies.

- House voice `house/2`. A published, versioned spec
  ([docs/house-voice.md](docs/house-voice.md), machine form
  `articulate/data/house_voice_v2.json`) written from reader-cost principles
  and cited research. No person's writing served as its model, and no
  AI-authorship detector was used to tune it. The brief a model reads is generated from the spec,
  so the spec, the brief and a receipt's fingerprint cannot drift apart.
  `house/1` stays packaged with its own fingerprint, so its receipts still
  verify; both versions share one edit list.
- Why `house/2`. In a blinded evaluation on a local 7B model with no tools,
  the `house/1` brief ("I read, I ran") led the model to claim checks it never
  ran in 15 of 60 replies, against 0 of 60 without the brief. `house/2` uses
  "I" only for actions the session's tool results show, never narrates a check
  without one, ends with what the reader should check, puts completeness before
  brevity, and on a request to write about the user's life or as the user uses
  only facts they gave, marks each missing fact as a gap such as
  `[your detail: when you started]` and asks for it. Re-measured on the same
  model and 30 prompts: untaken-action claims 0 of 60 with `house/2` and 0 of
  60 without it; median reply 133 words against 253.5 (86 with `house/1`); the
  AI-assistance line kept in 4 of 4 replies against 3 of 4.
- Off by default. The ship gate was: untaken-action claims no higher than with
  the brief off (at most 1 of 60), and a blinded reader not significantly
  worse. The shipped wording passed both. A blinded qwen2.5-coder 32B reader,
  shown each pair in both orders, preferred the plain reply on 18 of 60 pairs
  and the `house/2` reply on 9 (10 ties, 23 flipped with order; two-sided sign
  test p = 0.12). The reader still leaned toward the plain replies, and the
  shipped wording marked a gap in only 1 of 14 write-as-me replies. A variant
  that moved the life line up and named what not to invent marked a gap in 12
  of 14, but it failed the reader gate (21 to 8, p = 0.024) and put gap
  questions into 8 of 58 ordinary replies, against 1 of 58; it does not ship.
  Neither wording stopped this model from inventing life details (12 of 14
  replies with the shipped wording, 10 of 14 without a brief). So the house
  voice is opt-in: `ARTICULATE_HOUSE_VOICE=on` or `articulate house on`. An
  explicit `house apply`, `house brief`, `house_transform` or `house_brief`
  still applies it unless the user set a mode. Host models (Claude, Codex) and
  human readers are unmeasured.
- The plugin's new `SessionStart` hook hands the brief to the model at session
  start and after a resume, clear or compaction. It reads the spec and the
  settings file, imports none of the style rules and measured a 72 ms p95 on
  Windows. It is silent until the user turns the house voice on. A `Stop` hook ships declared and does nothing unless the user picks
  mode `revise`, which asks for one revision when a finished reply claims a
  human life or holds a HIGH style finding.
- `house_transform` (MCP), `articulate house apply` (CLI pipe) and
  `articulate.house.transform` (library) apply a closed list of exact edits to
  model output: em dashes that join two words to commas, doubled spaces, and
  opener and closer sentences with no content, such as a praise opener or an
  offer to help further. Dashes at a line edge, after a list marker or alone in
  a table cell stay, and a reply made only of such sentences is kept whole. An
  exact-edit verifier and the meaning guard check every candidate. Everything
  else is a located note, including `house/human-claim`. Receipts use
  `articulate/house-receipt/v1` and replay with `articulate verify`.
- Controls: `ARTICULATE_HOUSE_VOICE=off`, `articulate house off`, modes
  `off | brief | default | revise`, and tuning keys `length`, `headings`,
  `lists`, `first_person`, `limits` and `end_line`. The banned tics and the
  identity rules are not tunable.
- Personal voice. `articulate voice learn SAMPLES --name N --mine` builds a
  profile from the files you name, only after `--mine` says they are yours. The
  profile holds aggregates and no sample sentence, is bound to a local identity,
  stays in your local voice store, and `voice show`, `export`, `import`,
  `delete` and `delete --all` let you inspect, move and remove it.
  `voice compare` and `voice apply` refuse a profile that belongs to another
  owner.
- `voice apply DRAFT --name N --authored-by-me` (MCP `voice_apply_plan` with
  `authored_by_user: true`) plans an edit of your own draft toward your
  measured habits. Plans move to `articulate/edit-plan/v2`, which binds the
  profile name and hash and any author text; v1 plans still verify. A rewrite
  that adds a first-person sentence with no source in the draft or your own
  supplied words is refused paragraph by paragraph. Voice counts before and
  after are reported and never decide acceptance.
- Series review: `articulate corpus`, `titles`, `interview` and `restructure`,
  and the MCP tools `corpus_check`, `title_workshop`, `interview` and
  `restructure_plan`. Findings are report-only, with locations, a reader cost and
  a direction, never replacement prose. The interview asks and never answers;
  restructure keeps every sentence and citation byte for byte. Corpus receipts
  use `articulate/corpus-receipt/v1`.
- AI-assistance disclosures are a protected span kind. No rewrite, house edit
  or restructure moves or rewords one.
- New command `articulate-house-hook` for other hosts that run command hooks.
- `python -m articulate.bench house` reports a `python_start` row and a note
  when the interpreter alone starts slowly. In a clean Windows virtual
  environment every house budget holds (`house apply` cold, 2,000 words: 212 ms
  p95, budget 250 ms); the earlier Windows miss came from a machine whose
  site-packages runs about 120 `.pth` files at start-up.
- Codex: whether Codex runs `SessionStart` and `Stop` from a plugin is not
  confirmed. Open Codex issues report that plugin-local hooks do not run and
  that a root `plugin.json` disables them. `articulate house brief --agents`
  prints the brief as an AGENTS.md section as a fallback.

Claude plugin directory listing (merged on `release/0.5.x` before 0.8.0):

- The Claude plugin manifest carries the directory listing fields: a 1024 px
  icon, documentation, support, privacy and terms links, and the
  harperz9.github.io page as homepage. The privacy link moves from `metadata`
  to `privacyPolicyUrl`. The portable and Codex manifests leave the listing
  fields out. The plugin rules accept complete PNG and JPEG files and check the
  icon size and the listing links. Package code is unchanged.
- The plugin README's Privacy Policy, and PRIVACY.md with it, gains a section
  that names the edit hook, the MCP server launch, network use, files written,
  the bundled model backends that stay off, and each environment variable the
  server and hook read.
- The Claude plugin folder now carries the package modules its MCP server and
  edit hook import, at `claude-plugin/src/articulate`, so a directory install
  that receives only that folder starts. `python scripts/sync_plugin_source.py`
  regenerates the copy from `src/articulate`, and a test fails when the two
  differ. Another test copies the folder alone and runs the server launch and
  the hook command from the manifests. The privacy policy now says the hook
  ignores the session ID, transcript path and working folder in Claude Code's
  event.
- The Claude plugin no longer carries `editing.py`, `backends.py` or
  `claude_cli.py`, the model-backend modules that read provider API keys. The
  plugin's local tools never import them; `mcp_server` answers plainly when a
  model backend is asked for and the module is absent. The README install
  section now installs the `claude-plugin` folder as it is.

## 0.7.0

The source plugin checks prose at edit time in Claude Code and Codex. Detector
rules stay the published v0.5.2 rules; this release changes no finding.

- The source plugin adds an advisory edit-time hook for Claude Code and Codex.
  After the model writes or edits a prose file, the hook names numbers, links,
  quotes, citations, modals, scope words, negations and names that the edit
  dropped, added or changed, and lists style findings in the new text. It reads
  only the hook event, opens no file or connection, starts no program and never
  blocks the edit. `ARTICULATE_EDIT_HOOK=off` turns it off. The package adds an
  `articulate-edit-hook` command for other hosts that run command hooks.
  Each finding is cut to 240 characters and the whole answer to 6,000.
- The hook command was run the way Codex runs it on Windows. Codex replaces
  `${CLAUDE_PLUGIN_ROOT}` in the command text before it starts `cmd.exe /C`,
  so the command works under cmd.exe, Windows PowerShell and pwsh, including
  from a folder whose path has a space. Tests pin this, with a control that
  the unreplaced text fails. On Windows the hook needs Codex 0.145.0 or newer:
  earlier Codex escapes the quotes in the command and the hook does not run,
  though the edit still goes ahead.
- Tests pin two privacy and input controls on this line: any value of
  `ARTICULATE_LOCAL_ONLY` other than an explicit off value turns local-only on,
  and an empty file argument exits 2 with "no such file".

The hook names 16 of 19 critical changes and stays quiet on 7 of 8 ordinary
edits in the pre-registered synthetic set. It misses a changed file path, an
added intensifier and swapped subjects. No live Claude Code or Codex session
fired the hook end to end before release, and the tests do not show that a
model acts on the advice.

## 0.6.0

Articulate can ship as local Windows x64 tools with its Python runtime included.
The connected client supplies the model and rewritten text. Articulate includes
no model, requires no publisher-hosted service and adds no model account.

- Native ZIP and binary MCPB packages expose the local check and host-edit
  workflow. They reject launch arguments and external editor backends, even
  when inherited settings request them. Source plugins for Claude Code, Codex
  and portable MCP hosts remain separate and require installed Python.
- Rewrite guards check numeric bounds, modal force, scope and negation alongside
  protected spans. Code, math, quotes and HTML are masked before paragraph
  comparison. Refused edits retain the original text and return a receipt.
- Release builds retain the published v0.5.2 detector source and ruleset
  fingerprint. This release does not adopt the scanner changes withheld on
  the development branch. Retention establishes neither fairness nor quality.
- The shared release workflow builds and checks native and source-plugin
  packages before publication. Native release mode requires clean source,
  matching package versions and an exact version tag. Development mode stays
  explicit and labels its archives accordingly.
- An optional authenticated HTTP transport supports user-operated connections.
  It is off by default, adds no model and provides no publisher-hosted backend.
  Network access requires the user's own endpoint and permission configuration.

Local binary checks cover tool discovery, host edits, changed-number refusal
and backend refusal with Python absent from PATH. Client installation,
marketplace acceptance, clean-device compatibility and signing remain separate
qualification work. Guards can miss meaning changes and refuse valid paraphrases;
acceptance does not prove semantic equivalence or factual correctness.

## 0.5.2

Local-only MCP sessions can use the calling model through editor aliases.
Detector rules and protected-span matching remain unchanged from 0.5.1.

- `fix`, `judge` and `polish` return a host plan for default, auto and host
  selection in local-only mode. Deterministic editing remains available;
  explicit sampling and network backends are refused before resolution.
- The local plugin supplies nine tools with titles and safety annotations,
  UTF-8 stdio handling, capped findings and host-edit workflow skills.
- Plugin release builds require the package version tag to exist locally and
  resolve to a commit before checking source parity. Missing tags stop the build
  before output is written; `--dev` remains an explicit local test path.

The checker makes no network call in this local mode. The calling host still
processes the conversation under its own data policy. A protected-span check
does not prove semantic equivalence or factual correctness.

## 0.5.1

The editor can use the calling model, a configured endpoint or deterministic
editing. An unavailable Claude account no longer ends the editing workflow.
Detector rules remain unchanged on this patch line.

- MCP `edit_plan` and `edit_submit` let a calling model edit with no second
  account. Plans bind the source and configuration to a ruleset; submission
  checks that binding, restores masks and reports protected-span refusals.
- MCP automatic selection uses sampling only when the client advertises it,
  otherwise returning a host edit plan. CLI automatic selection tries configured
  Anthropic, the Claude CLI, configured OpenAI-compatible endpoints, Ollama and
  deterministic editing. Failed attempts are recorded without credentials.
- `none` applies conservative mechanical fixes and reports remaining findings.
  Its judge reports local reasons without model quality scores. Ollama uses
  installed models and never pulls one.
- Every rewrite passes the protected-span guard. Refused spans retain their
  original text; gate and per-rule changes are reported. Protected content
  surviving a rewrite does not prove unchanged meaning.
- `ARTICULATE_LOCAL_ONLY=1` allows only loopback Ollama and deterministic editing,
  refusing other editor backends before a connection. Host and sampling paths
  follow the calling host's privacy policy when local-only mode is off.
- CLI `plan`, `submit`, `fix`, `judge` and `polish` expose these paths. Legacy
  `python -m articulate.editor` commands remain available with `--backend`.
  Results and editor receipts name the backend, model and failed attempts.

## 0.5.0

A document folder can no longer run commands through `judge`, `fix` or
`polish`. Detector findings and the ruleset fingerprint do not change.

In 0.4.2 the `claude -p` child started in the caller's working directory. The
CLI reads `.claude/settings.json` from there, and `-p` skips the workspace trust
prompt. So a document folder that shipped a settings file ran its command hooks
on every editor call, on every platform, and its `env` block reached the
session. On Windows an npm `claude.cmd` shim added a second path: it runs
`node` by bare name, and cmd.exe looked for `node` in the working directory
before the PATH.

- The CLI now starts in a new private folder that `tempfile.mkdtemp` creates.
  That folder holds the prompt file and an empty working folder for the child,
  and the editor removes it after the call.
- Every call now passes `--setting-sources user`, so project and local
  settings never load. The full list is
  `--setting-sources user --strict-mcp-config --tools ""`.
- On Windows the child's environment sets `NoDefaultCurrentDirectoryInExePath=1`,
  so cmd.exe finds the shim's `node` on the PATH only.
- For a batch shim, `)` in an unquoted argument is now refused too. cmd.exe
  reads it as the end of a parenthesized block. A path with a space, such as
  one under `Program Files (x86)`, is quoted and still runs. The check covers
  the prompt file's path as well as the CLI path, so a `TEMP` folder with `&`
  in its name is refused.
- A temporary folder that cannot be written now raises `ClaudeUnavailable`,
  and the message leaves out the path. In 0.4.2 the `OSError` escaped as a
  traceback.
- The editor searches the CLI's output for backend errors, such as a rate
  limit, only when the call fails. A `fix` of a document that mentions rate
  limits used to fail as `ClaudeUnavailable`. A call that exits nonzero now
  always fails, even when it printed output.
- An older CLI that rejects one of the flags now raises `ClaudeUnavailable`
  with a message that says to upgrade. The flags are tested with CLI 2.1.251.
  The first version that accepts all of them is unknown.

Breaking for callers:

- This release carries the minor version that 0.4.2 should have had. The
  0.4.2 changes for callers below were breaking, and a `~=0.4.1` pin picked
  them up as a patch.
- The runner that `claude_cli.run` calls now receives `cwd` and `env` keyword
  arguments. A test double must accept them.

Tests: the new `tests/test_claude_cli_batch.py`, `tests/test_claude_call.py`
and `tests/test_no_shell_calls.py` and the updated CLI tests cover each change.
A unit test checks that the child's working folder is new, empty and apart
from the prompt file. A process test starts a stand-in from a folder that holds
`.claude/settings.json` and checks where it ran. A Windows test runs npm's own
`claude.cmd` template with a `node.cmd` planted in the caller's folder. A
Windows test runs every punctuation character through cmd.exe and checks that
the refused set matches what cmd.exe changes. The shell-call scan now also
catches `**` keywords on process calls, a command whose first word names a
shell, `COMSPEC` and `os.posix_spawn`. Each of those has a sample it must catch.

Checked by hand, not in CI: the real CLI 2.1.251, started through
`claude_cli.run` from a folder with project `SessionStart` and
`UserPromptSubmit` hooks and with the API address on a closed local port, ran
both hooks under 0.4.2 and neither under this release. Not tested: whether a
folder's `env` block could have sent requests to another host, or whether a
`CLAUDE.md` there steered the judge. Both need files in the caller's folder,
which the CLI no longer reads.

## 0.4.2

The editor commands `judge`, `fix` and `polish` now find the `claude` CLI in
more setups, and the model call runs with no tools. Detector findings and the
ruleset fingerprint do not change.

The editor started the CLI by the bare name `claude`. That failed in two cases.
A process that an MCP host or a bundled app starts can inherit a PATH that
holds only System32. And on Windows, subprocess without a shell looks only for
`claude.exe`, so it never found the `claude.cmd` shim that an npm install puts
on the PATH. In both cases the start raised an uncaught `FileNotFoundError`.

- New module `articulate.claude_cli` resolves the CLI. The environment variable
  `ARTICULATE_CLAUDE_CLI` names its path and wins when set. Its value must be an
  absolute path; a bare name or a relative path is refused.
- Otherwise the resolver walks the absolute PATH entries itself. It takes
  `claude.exe` from any entry first, and a `claude.cmd` or `claude.bat` shim
  only when no entry holds `claude.exe`. So a setup that ran `claude.exe`
  before still runs it, whatever the PATH order. The current directory is never
  searched, and neither is a `.` or empty PATH entry. On Windows,
  `shutil.which` looks in the current directory first, so a document repo that
  shipped a file named `claude.cmd` would have run in place of the real CLI.
- When nothing runnable is found, the editor raises `ClaudeUnavailable`. Its
  message names the variable and says the CLI must be installed and logged in.
  A start that fails with an `OSError` raises the same error. No message prints
  the value of the variable or the resolved path. A timeout message names only
  `claude`.
- The prompt now travels in a temporary file passed with
  `--append-system-prompt-file`, on every path, and the file is removed after
  the call. The argument list holds a fixed line, that path and fixed flags. A
  prompt with many detector findings could pass the Windows command-line limit
  of about 32K characters, which failed with a misleading "could not be
  started" error. And a `.cmd` file runs under cmd.exe, which cuts an argument
  at the first newline and treats `%`, `^`, `&`, `|`, `<`, `>` and `!` as
  commands. For a batch file, a path with one of those characters is refused.
- Every call passes `--strict-mcp-config --tools ""`, so the model session has
  no built-in tool and loads no MCP server. The document is untrusted input,
  and before this change the `claude -p` child inherited the user's allow
  rules and MCP servers.
- A timeout now stops the whole process tree: `taskkill /F /T` by its System32
  path on Windows, a process-group kill elsewhere. Before, a timeout on a batch
  shim killed only cmd.exe and then waited for the CLI to finish.
- `polish` now catches a judge failure inside its rewrite loop, such as a rate
  limit halfway through, keeps the best version so far and exits cleanly.
  Before, that failure ended in a traceback.

Changed for callers. These changes are breaking, and the release should have
raised the minor version; 0.5.0 carries that bump:

- The model's instructions now arrive as an appended system prompt, and the
  user turn holds a fixed line. The trust boundary text still ends the
  instructions, and the document stays on stdin.
- `editor.CLAUDE` is removed, and setting it has no effect. The variable
  `ARTICULATE_CLAUDE_CLI` now names the CLI.
- `editor.run` is removed. A test double that patched it would now reach the
  real CLI. A double now patches `articulate.claude_cli.run`.
- A missing CLI raises `ClaudeUnavailable`, a `RuntimeError`, where it used to
  raise `FileNotFoundError`, an `OSError`. `ClaudeUnavailable` moved to
  `articulate.claude_cli`; `articulate.editor` still exports it.
- `claude_cli.resolve` reads PATH from the `environ` mapping it is given.

Tests: `tests/test_claude_cli.py` and `tests/test_claude_cli_process.py` cover
the resolution order, a `claude` planted in the current directory, the closed
errors, the fixed argument list, every character cmd.exe reinterprets for both
`.cmd` and `.bat`, a 40,000-character prompt, and a timeout that must return
within 5 s while a grandchild sleeps. A parse of every source module checks
that no call asks for a shell. CI now also runs the suite on `windows-latest`,
where the stand-ins go through cmd.exe.

Not verified: a model reply through the batch path. A stand-in `claude.cmd`
around the real CLI 2.1.251 accepted the new arguments and reached the
backend, which answered with a credit error on the test machine.

## 0.4.1

Fixed quadratic run time in the markup masks. Findings do not change, and the
ruleset fingerprint does not move.

Before the prose passes run, the detector blanks URLs, e-mail addresses, and HTML
tags on every line, plus quoted speech under a dialogue-exempt genre. It did this
with `re.sub` and patterns that backtrack quadratically on a long line where a
match never completes. `strip_markup` runs up to six times per line, so one such
line stalled `check_text` far past the 3 s budget the ReDoS test enforces.

Time for one `check_text` call, before and after:

- `"v1." * 10000` under flavored: 16.0 s before, 0.08 s after.
- `"1.1.1.1." * 5000` under flavored: 53.2 s before, 0.14 s after.
- `("1.1.1.1." * 5000) + "@"` under flavored: 47.8 s before, 0.14 s after.
- `"twenty-" * 8000` under flavored: 29.5 s before, 0.08 s after.
- `"<a " * 40000` under flavored: 23.5 s before, 0.33 s after.
- `"\u201ca " * 20000` under literary-fiction: 13.6 s before, 0.21 s after.

Before and after were measured on one machine, each pair in one session. That
machine was under load from other work, so the absolute numbers are noisy.

- The e-mail part of the URL pattern retried every word boundary inside a long
  run of word characters, dots, or hyphens, and rescanned the rest of the run
  each time. The tag pattern rescanned to the end of the line from every
  unclosed `<`. The quote pattern did the same from every unclosed curly quote.
- New module `articulate.masking` returns exactly what `re.sub` returns with
  each pattern, in linear time. The e-mail scan tests each run once, because
  every start inside one run succeeds or fails together. The tag mask stops at
  the last `>` in the line, since no tag can start after it. The quote mask
  skips an opening mark once one of its kind has failed to close before the
  next newline.
- The patterns themselves are unchanged and remain the definition of record as
  `detector.URL`, `detector.TAG`, and `detector.QUOTED`. `tests/test_masking.py`
  compares each mask with `re.sub` on 4,000 generated lines and a set of hand
  cases. It also holds each mask, and the detector functions `strip_markup` and
  `mask_quotes` that apply them, to 0.25 s per call on long hostile lines, so a
  call site that goes back to `re.sub` fails as well.
- `tests/test_redos.py` adds the inputs above, so the 3 s per-input budget now
  covers them. The tag and curly-quote inputs use 40000 and 20000 repeats. With
  10000 repeats the old code took 0.3 s to 0.6 s on the tag input and 3.3 s to
  5.0 s on the quote input, so a regression there could pass the budget.
- Checked for identical output: full `check_text` results (rule ids, spans,
  labels, gate, texture, cadence) and per-line masks were compared before and
  after on every tracked file except the VS Code extension's lockfile, under no
  profile and under all 18 profiles, 6 genres, and 29 modes. The same check ran
  on 612 further documents (Markdown, HTML, SVG) under 9 configurations. No
  result differed. The benchmark output is byte-identical.
  The fingerprint hashes the tier patterns and leaves the mask patterns out. It
  reads `sha256:9f78a7484bb20f84` before and after, so `RULESET_SEMVER` stays
  0.5.0.

Tests: 181 pass.

## 0.4.0

Added a stdio MCP server that runs from a bare install.

The existing MCP surface is built on fastmcp, which is declared under the `mcp`
extra. A plain `pip install articulate-writing` produced a package whose MCP
entry point raised `ModuleNotFoundError: No module named 'fastmcp'` the moment a
host launched it. The install reported success and the server never started.

- `articulate.local_mcp` serves the same five tools over stdio JSON-RPC 2.0
  (protocol `2025-06-18`) with nothing but the standard library, plus
  `articulate.status` and `articulate.doctor`. `doctor` reports which tools run
  local (`check`, `score`) and which need an LLM backend (`judge`, `fix`,
  `polish`), so a host with no backend knows what it still gets.
- New console script `articulate-mcp`. The fastmcp server stays available under
  the `[mcp]` extra as `articulate.mcp_server`.
- The tool bodies are unchanged and shared. Both transports call the same
  `do_check`, `do_score`, `do_judge`, `do_fix` and `do_polish`, and a test parses
  the fastmcp module for its `@mcp.tool` functions to assert the stdio server
  exposes every one of them. The two surfaces cannot drift apart.
- `tests/test_version_alignment.py` binds `pyproject.toml`, `articulate.__version__`
  and the version the MCP server reports. The three had no guard tying them
  together, so a release could ship reporting the previous version.
- The publish workflow now pins every action by commit SHA. A tag can be moved to
  point at different code, which matters in a workflow that holds publishing
  authority. It also checks the release tag against the declared version, records
  artifact digests, resolves every console script in a clean venv, and rebuilds a
  wheel from the sdist before uploading.

## 0.3.0

Added three cadence detectors for prose that reads clean under the earlier ruleset
yet still carries a machine rhythm a reader hears.

- Demonstrative summary-beat, "That is the ... half / side / piece / layer / angle
  / story / trick". Tier MEDIUM, so it gates under a strict profile. A compound noun
  like "That is the side effect" and a plain "That is the file" do not fire.
- Two-imperative parallel slogan, "Verb the X, verb the Y." Tier LOW and advisory,
  since an everyday instruction is often an imperative pair. It anchors to a full
  line of two comma-joined bare-verb clauses, and a determiner or pronoun opener
  blocks it.
- Evaluative fragment opener, "Strong foundation." Tier LOW and advisory,
  paragraph-initial only, and fragment-shaped so a full sentence does not match.

Detector internals:

- Ruleset semver moves 0.4.0 to 0.5.0, and `FRAGMENT_OPENER` folds into the ruleset
  fingerprint, so a replay against an older receipt reports the ruleset change
  explicitly.
- A verse genre suppresses the two new LOW categories.
- Every new pattern uses bounded quantifiers and stays covered by the ReDoS safety
  test.
- The demonstrative extension fires on none of a 26-snippet human control corpus.

Tests: 151 pass.

## 0.2.0

Detector expanded to the full device catalogue. It reached 18 HIGH, 55 MEDIUM, and
12 LOW tells, plus 7 standard-library statistical advisories. The tells cover
lexical and structural devices, cadence, delivery, and formatting.
False-positive-controlled against a 22-snippet human corpus with zero false HIGH or
MEDIUM. Ruleset semver 0.4.0. Tests: 143 pass. Published to PyPI as
`articulate-writing`.

## 0.1.0

First public release. The core detector, register profiles, writing modes, the
genre axis, per-span mixed-authorship verdicts, an "unverifiable" sub-threshold
calibration, binary fail-closed input guards, the benchmark, the editor layer, the
CLI, the LSP and SARIF surfaces, receipts, the content-free audit receipt, and the
MCP server. The core runs standard-library-only with no network call.
Source-available under FSL-1.1-MIT. Published to PyPI as `articulate-writing`.
