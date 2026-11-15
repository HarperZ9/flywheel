# Features

Each section names what the feature gives you and how to reach it. For the exact
commands and flags, see the [CLI reference](cli.md). For what a verdict and a
receipt mean, see [Boundaries](boundaries.md).

## The deterministic detector

The core reads prose and flags the tells that make text read as generated, in
three confidence tiers:

- HIGH: banned rhetorical devices (antithesis, corrective negation, the triad,
  negative parallelism, em-dashes) and named register words. These are hits.
- MEDIUM: strong tells of current frontier-model prose, the stock transitions,
  the marketing superlatives, the participial closers, the email and blog tells.
- LOW: advisories that catch a real pattern and also fire on innocent prose, so
  they report, leave the gate open, and expand with `--verbose`.

It also carries keyword-free detection for a parallel-negation contrast pair, and
document-level signals for uniform cadence, repeated sentence openers, passive
density, and adverb density. Every finding carries a line, a column, and a
character span, so an editor can place a squiggle and a receipt can pin the exact
location.

Alongside the pass or fail gate, it emits a graded 0 to 100 texture score that
accumulates weak evidence by density. The score is a signal for grading and for
the benchmark. The clean or flagged verdict comes from the gate.

## Register profiles

A profile is a register configuration expressed as data. It sets which detector
tiers block, a list of terms of art the detector never flags, and provenance
fields. The shipped profiles cover procedures, commits, error messages,
changelogs, release notes, API docs, specs, research, proofs, model cards,
readmes, legal text, journalism, social copy, chat, essays, and narrative. The
domain profiles below add rule packs for UI microcopy, code review comments,
plain language, controlled English and RFC keywords.

The gate follows a slop level. `off` reports every finding and leaves the gate open, for
narrative where authorial voice governs. `flavored` blocks the HIGH device tier, for docs and research.
`strict` blocks HIGH and MEDIUM, for procedures and essays that must be device
free. A profile resolves from an explicit flag, an in-file `writing-profile:` tag,
or the file path.

## Domain profiles

Some kinds of writing have rules of their own. A domain profile is a register
profile plus a rule pack: deterministic rules for that kind of writing. The
packs run after the detector, outside its published rules, so the v0.5.2
detector and every register profile keep their findings. Pack findings gate,
report and export like any other finding, and they never change the texture
score. A rule whose judgment is a heuristic sits in the LOW tier and reports
without blocking. Every numeric default is a pack option, set under `options`
in the [project config](#project-config), and the source of each default is
named below. All of these rules read English only.

Choose one with `--profile NAME`, an in-file `writing-profile: NAME` tag, or a
project config glob. Receipts record the domain profile name and an
`extension_fingerprint`, a hash of the packs, their defaults and the domain
profile definitions. A receipt whose packs have since changed reads
`Unverifiable`.

- `ux-microcopy`: UI strings. The `flavored` keep list, strict gate.
- `code-review`: review comments. The `flavored` keep list plus nit, lgtm,
  blocking, non-blocking and suggestion, flavored gate.
- `plain-language`: readability. The `flavored` keep list, strict gate.
- `controlled-english`: controlled English. The `flavored` keep list, strict
  gate.
- `rfc-keywords`: RFC 2119 and RFC 8174 keywords. The `normative-spec`
  profile, flavored gate.
- `product-copy`: READMEs, release notes and listings. The `readme` profile,
  flavored gate.
- `note`: a personal note to someone you know. The `chat` profile, flavored
  gate, with a stock opener and a stock closing offer promoted to the gate.
- `author-voice`: your own first-person writing. The `narrative` profile, so
  no device gates, with em-dashes still reported.
- `publication`: research and published findings. The `research` profile plus
  claim evidence and advice on analogies, flavored gate.
- `outbound`: text about to leave your machine, such as a message, a post or
  a pasted report. The `chat` profile, flavored gate, with e-mail addresses
  and local paths promoted to the gate.

### `outbound` and the `privacy` pack: personal details before text leaves

- `private-email` (MEDIUM): an e-mail address. Reserved example domains
  (`example.com`, `.test`, `.invalid`, `.localhost`) and no-reply addresses
  are left alone.
- `local-path` (MEDIUM): a path on one computer, such as a Windows drive path,
  a home folder under `/Users` or `/home`, or a network share. It shows the
  machine's layout and often the account name.

The pack reads the whole text, code blocks and inline code included, because a
path in a code block leaves with the text too. `outbound` gates on both
categories. `note`, `product-copy` and `publication` run the pack and report
without gating, since a contact address there can be deliberate. The patterns
are closed: an address with its @ spelled out, or a path written another way,
is not caught. Run `articulate check --profile outbound FILE` before you send.

### `product-copy`: what the tool does for the reader

- `claim-without-evidence` (LOW): a claim a reader would want to check, such as
  "10x faster than", "production-ready" or "secure by default", with no link,
  code, file, figure or counted number in the same or the next sentence. The
  label gives the document's coverage, for example "4 of 6 claim sentences here
  point at evidence", so the share is read with its count.
- `lead-author-framed` (MEDIUM): the first sentence talks from the maker's side
  ("I built", "my tool") or opens on what the tool lacks.
- `mission-missing` (LOW): 150 words or more and no stated mission.

The profile keeps and freezes the author's own words for the tools: distill,
essence, layers, weights, metamers, lens, boundary, signal, noise and "make
truth cheap to check". For the share of a description spent on what a tool
lacks, run `articulate negation`.

### `note`: a note to someone you know

- `note-opener` and `note-closing-offer` (MEDIUM, gating): "I hope this finds
  you well", "let me know if you have any questions" and their kin.
- `note-professional` (LOW): office words such as "regarding" and "kindly".
- `note-length` (LOW): past the word budget, 120 by default.

### `author-voice`: your own register, kept

Literary devices are tools here. `articulate devices --function` names each
one, adds simile, metaphor and motif, and reads the sentence for an image (a
thing a reader can picture), an anchor (a number, a quote, a name, a file) or a
stance (because, I think, I saw). A device that carries one reads `carries`.
One that carries none, or rests on a stock vehicle such as "journey" or
"beacon", reads `empty`, and the check reports it as `device-empty` (LOW). Irony
and synecdoche need context these readers cannot see, and the report says so.

Analogy has its own reading. It `carries` when it maps two or more parts onto
something the reader knows ("the reviewer is the co-pilot, the diff is the
checklist") or carries a relation across ("a token is to a server as a key is
to a lock"). A bare stock comparison ("like a rollercoaster") reads `empty`. A
comparison inside one domain with real figures ("build 2 runs in 2.1 seconds,
like build 1") is not read as a device.

The register is measured by `articulate.voice_register`: imagery, forward
motion, runs of ideas, the observer's "I saw", first person, questions,
contrarian turns, jaded and wondering words, the defensive guard, plain
profanity, analogies that carry structure, symbolic messaging ("the scale of
justice we all hold") and confrontation that holds the reader to their own
contradiction ("you say ..., but you ..."). An edit planned under this profile keeps the original text when the
rewrite loses one of them, and `voice apply` does the same unless you pass
`accept_register_change`. `articulate voice register DRAFT REWRITE` prints what
a rewrite kept and lost. Claims are still checked against evidence. The
built-in intent spec `author-voice` (`articulate voice check DRAFT --intent
author-voice`) wants the same features and sets no limit on devices.

### `publication`: analogies that point at a map

- `analogy-untested` (LOW, advice): an analogy that carries the argument with no
  pointer to a testable map in its sentence or the next. A pointer names what
  corresponds to what, where the map breaks, what it predicts, or links to the
  work that tests it. It never gates.

### `ux-microcopy`: UI strings

One UI string per line. A `button:`, `label:`, or `error:` prefix sets the type,
or a resource key does (`"save_button": "Save"`).

- `ux-length` (MEDIUM): a button over 3 words or 26 characters, a label over 4
  words, an error sentence over 25 words. Button words follow Material Design 3
  ("ideally 1-3 words"), button characters follow Microsoft's Windows button
  guidance (26 characters), and error sentences follow GOV.UK's 25-word split.
  The 4-word label limit is Articulate's own default, with no published number
  behind it.
- `ux-case` (LOW): title case where the project uses sentence case (Material
  Design 3, the Microsoft Style Guide). Apple's guidelines use title-style
  buttons, so `case` takes `sentence`, `title`, or `off`. A proper noun reads like
  title case, so this reports only.
- `ux-vague-error` (LOW): an error that lacks a next step and is vague or leaves
  out its cause, after the Nielsen Norman Group error-message guidelines.
- `ux-link-text` (MEDIUM): "click here", or link text such as "here" or "learn
  more", after the W3C tip against "click here" links. WCAG applies the rule
  strictly at level AAA (failure F84 under success criterion 2.4.9); at level A,
  link text may lean on its context.

```
[articulate] strings.txt [ux-microcopy]: 0 high, 4 medium (blocked)  texture 0/100
  L1 [MEDIUM ux-length] button label has 7 words and 34 characters; the limit is 3 words and 26 characters: button: Save And Continue To The Next Step
  L5 [MEDIUM ux-link-text] link text that names no destination; name where the link goes: link: For details, click here.
```

### `code-review`: review comments

A flavored gate, so these report and the banned devices still block.

- `review-condescension`: "just", "simply", "obviously", "clearly" (LOW), and
  stronger markers such as "why didn't you" or "any competent developer" (MEDIUM).
- `review-no-reason` (LOW): a request ("please rename", "can you move", "this
  should be") in a comment that lacks a reason anywhere in it.
- `review-absolute` (MEDIUM): absolute language about a person, such as "you
  always", "you never", or "your code is wrong".

These are phrase lists. They catch the listed wording; a paraphrase and tone
need a human reader.

### `plain-language`: a readability gate

- `plain-readability` (MEDIUM): the document's Flesch-Kincaid grade is above
  `max_grade` (default 8). The finding names the grade and the reading ease and
  anchors on the hardest sentence.
- `plain-long-sentence` (LOW): a sentence over 25 words (GOV.UK's split).
- `plain-wordy` (LOW): a wordy phrase with a plainer form, such as "in order
  to" for "to". The list is curated for this tool.

Where grade 8 comes from: Microsoft Word's readability help recommends a grade
score of "around 7.0 to 8.0". No US federal rule sets a number. The Plain Writing
Act of 2010 defines plain writing without a score, and the Federal Plain Language
Guidelines argue against a blanket grade. Health guidance aims lower: AHRQ's
health literacy toolkit points to a 4th to 6th grade level for patient
materials, so a health team should set `max_grade` to 6. Below `min_words`
(default 100, Articulate's own floor) the grade is too unstable to gate on, and
the rule stays silent. Syllables are estimated, so the grade can differ from
another tool's by a grade or more, and a low grade shows short words and short
sentences, which is not the same as a reader understanding the text.

### `rfc-keywords`: RFC 2119 and RFC 8174 keywords

The `normative-spec` register plus a check of BCP 14 keyword use. The
`normative-spec` profile on its own keeps its published findings and runs the
register checks alone. RFC 8174 gives the keywords their special meaning in all
capitals, and asks a document that uses them to say so in a boilerplate sentence
citing BCP 14.

- `bcp14-mixed-case` (HIGH, gates): "MUST not", "SHOULD not", "must NOT",
  "NOT recommended".
- `bcp14-no-boilerplate` (MEDIUM): capital keywords in a document missing a
  citation of BCP 14, RFC 2119, or RFC 8174.
- `bcp14-may-not` (MEDIUM): "MAY NOT", a form both RFCs leave undefined.
- `bcp14-lowercase` (LOW): a lowercase "must", "shall", or "should" in a document
  that declares BCP 14. Lowercase "may", "required", "recommended", and
  "optional" are left alone as common plain words.
- `bcp14-shall-must` (LOW): both SHALL and MUST in one document.
- `bcp14-old-boilerplate` (LOW): a declaration without the RFC 8174 clause
  "when, and only when, they appear in all capitals".

Quoted keywords, such as those listed in the boilerplate itself, are skipped.
The rules check keyword form; whether a requirement is the right one is for the
spec's reviewers.

### `controlled-english`: second-language readers and translation

Inspired by controlled-language practice in technical writing. The rules borrow
two sentence-length limits from ASD-STE100 and use Articulate's own short word
lists. For ASD-STE100 conformance, use the specification and its dictionary.

- `controlled-sentence-length`: a sentence over 25 words (MEDIUM), or an
  instruction over 20 words (LOW, because spotting an instruction is a
  heuristic). The two limits follow the published sentence-length rules of
  ASD-STE100 Issue 9 (rules 5.1 and 6.3), and both are options.
- `controlled-multi-instruction` (LOW): two instructions chained in one sentence.
- `controlled-idiom` (LOW): an idiom a translation engine may read word by word,
  with a literal form.
- `controlled-phrasal-verb` (LOW): a phrasal verb with a single-word form, such as
  "find out" to "learn".
- `controlled-vague-pronoun` (LOW): a sentence that opens with "This", "That",
  "These", or "It" followed directly by a verb, as in "This means".

The idiom and phrasal-verb lists are Articulate's own and are short. A clean
result means the text passed these lists. A translator's review is what certifies
a text for translation.

### Sources for the domain defaults

Each page was read on 2026-09-23, when these defaults were set. A source can
change after that date, so check it before you rely on a default.

- Material Design 3, button guidelines: <https://m3.material.io/components/buttons/guidelines>
- Microsoft, Windows button controls: <https://learn.microsoft.com/en-us/windows/apps/develop/ui/controls/buttons>
- Microsoft Style Guide, capitalization: <https://learn.microsoft.com/en-us/style-guide/capitalization>
- Apple Human Interface Guidelines, buttons: <https://developer.apple.com/design/human-interface-guidelines/buttons>
- Nielsen Norman Group, error-message guidelines: <https://www.nngroup.com/articles/error-message-guidelines/>
- W3C, "Don't use 'click here' as link text": <https://www.w3.org/QA/Tips/noClickHere>
- GOV.UK, clear language: <https://guidance.publishing.service.gov.uk/writing-to-gov-uk-standards/writing-guidelines/clear-language/>
- Microsoft Word, readability statistics: <https://support.microsoft.com/en-us/word/get-your-document-s-readability-and-level-statistics-in-microsoft-word>
- Plain Writing Act of 2010: <https://www.govinfo.gov/content/pkg/PLAW-111publ274/html/PLAW-111publ274.htm>
- AHRQ Health Literacy Universal Precautions Toolkit, Tool 11: <https://www.ahrq.gov/health-literacy/improve/precautions/tool11.html>
- RFC 2119 and RFC 8174: <https://www.rfc-editor.org/rfc/rfc2119.txt>, <https://www.rfc-editor.org/rfc/rfc8174.txt>
- ASD-STE100: <https://www.asd-ste100.org/>

The Flesch-Kincaid and Flesch reading-ease formulas trace to Kincaid, Fishburne,
Rogers, and Chissom (1975), Research Branch Report 8-75. The coefficients here
match the ones Microsoft's readability page reproduces. The source for them is
that page; the 1975 report itself was unavailable for this check.

`python -m articulate.bench` also runs the domain regression corpus under
`corpus/domains/`: short synthetic samples, each with the exact set of pack
categories it must produce, and each clean sample must come back empty and pass
its gate. The corpus is a regression check: it shows the rules still do what
they did. Recall and precision on real documents are measured in
`corpus/provenance/`.

## Project config

A project sets its own rules in a `.articulate.json` file. Articulate finds it
by walking up from each checked file's directory, and the nearest file wins; for
standard input the search starts in the current directory. `--config PATH`
names a file, and `--config none` turns discovery off. With no config file,
every command's output is the same as before project configs existed. The
format is JSON because the package supports Python 3.9, and a TOML parser
joined the standard library only in 3.11.

```json
{
  "version": 1,
  "profiles": {"docs/api/**": "api-docs", "ui/*.txt": "ux-microcopy"},
  "terminology": {
    "banned": [{"term": "whitelist", "suggestion": "allowlist",
                "reason": "inclusive language"}],
    "preferred": [{"use": "sign in", "instead_of": ["log in", "login"]}],
    "allowed": ["leverage"]
  },
  "freeze": ["Articulate"],
  "options": {"plain-language": {"max_grade": 6}, "ux-microcopy": {"case": "title"}}
}
```

- `profiles` maps a path glob, relative to the config file, to a register
  profile, domain profile, genre, or mode. The first matching glob wins. It ranks
  below `--profile`, `--mode`, and an in-file `writing-profile:` tag, and above
  inference from the path.
- `terminology` adds project rules to every check. A banned term fires as rule
  `terminology/banned/<term>` (HIGH by default), and a replaced variant fires as
  `terminology/preferred/<preferred form>` (MEDIUM by default). Each entry may set
  its own `severity` and `match_case`, and the finding carries the reason and the
  suggestion. Code spans, URLs, and fenced blocks are skipped. The rule ids show
  in `check` text, `--json`, `--sarif` and `--spans`, in LSP diagnostics, and in
  receipts. These rules run after the detector, like the domain rule packs, and
  never change the texture score.
- `allowed` terms join the profile's terms-of-art keep list. They clear the
  vocabulary and register rules; a structural device such as antithesis still
  fires on them.
- `freeze` terms must survive every rewrite unchanged. The edit plan binds them
  (plan schema `articulate/edit-plan/v3`) and the guard reads them as protected
  spans of kind `term`.
- `options` tunes a domain rule pack by name (`ux-microcopy`, `plain-language`,
  `controlled-english`). An unknown pack, option, or value is an error.

Protected spans are always on in this release, so the config has no `protect`
key, and a config that names it is rejected with a message saying so. Disclosure
lines and the added-first-person guard are permanent.

A malformed file stops the command with exit 2, the file name and the reason:
invalid JSON, an unknown key, a bad type, an unknown profile, or a term that is
both banned and allowed. The LSP server reports
a broken config as a diagnostic on line 1 and checks the document without it.
`articulate config PATH` prints which config applies to a file, the profile it
chooses and why, the terminology rules, the freeze terms and the pack options.

A receipt made under a config embeds the terminology and options as
`project_rules` with their hash, so anyone can replay it from the receipt
alone. An edited rule set reads `Unverifiable`, and a consistently re-hashed
edit that changes the findings reads `Drift`. A receipt made with no config has
neither field.

## Writing modes

A mode crosses a domain register with an articulation need, what the prose does to
the reader: explain, persuade, instruct, narrate, argue, or prove. A mode is a
base profile plus a small delta: terms of art to keep, categories to block even
under a lenient base, and editor guidance. Run `articulate modes` for the list.

A mode tunes style within the plain-writing standard. It may tighten the gate and
add terms of art. The banned devices stay banned on prose under every mode;
literary narrative is the one register where the gate is off.

## The genre axis

Narrative and expressive prose read by their own convention, so a scanner tuned
for an essay misreads a novel. The genre axis adds `literary-fiction`,
`genre-fiction`, `ya-fiction`, `memoir`, `screenplay`, and `poetry`. Under a
fiction genre:

- Quoted speech is masked out of the device passes, so a character's line is
  scored as that character's voice and left out of the author's prose.
- The craft devices report and leave the gate open, because voice governs.
- A report-only lexicon flags generation artifacts, such as the somatic cliche or
  the "could not help but" reflexive.

Screenplay classifies Fountain roles first, so only action lines face the device
gate and dialogue keeps the character's voice. Poetry reads by the line, and the
craft-device categories drop from its report, because they name legitimate
technique in verse.

## Markdown structure

Some Markdown is not prose, and Articulate blanks it before the rules run. The
masks keep every offset, so a finding still points at the right line and column.

- A table delimiter row such as `| :--- | ---: |` is skipped. A dash inside a
  table cell still fires.
- Fenced code, an indented code block outside a list, and YAML or TOML front
  matter are skipped.
- Inline math such as `$a---b$` or `$$x -- y$$`, and a display block between two
  `$$` lines, are skipped. A dollar amount stays prose. An opening `$` needs a
  non-space after it, and a closing `$` needs a non-space before it and no digit
  after it, so "$5 and $10" and "$5-$10" stay prose. An escaped `\$` never opens
  or closes a span.
- A register word inside a run of capitalised words, such as `Transformative` in
  `the Transformative AI Fund`, reads as a name and is skipped. At the start of a
  sentence every word is capitalised, so the word still fires there, unless the
  same capitalised run appears elsewhere in the document away from a sentence
  start. `Robust Intelligence builds models.` alone is still flagged.

Block quotes are checked as prose. A quote can be a cited source, and it can
also be the author's own callout or pull quote, and the Markdown does not say
which. Checking both keeps the author's own words from slipping past the gate.
To quote a source verbatim without findings, put it in a fenced block, which
the checker skips. A term the project accepts in every file goes in the
`allowed` list of the project config.

A receipt records the mask set as `structure`. `markdown/1` is the set in 0.14.0,
and `markdown/2` adds the math masks and the sentence-start names. A receipt
replays under the set it names, so a receipt from 0.14.0 still reads Match.

## Science and mathematical writing

`academic/prove` and `science-writing/explain` target hard technical exposition:
stating the idea before the formalism, keeping a roadmap, defining each symbol
once. On a `.tex` file the editor masks every math span before a rewrite and
splices it back byte for byte, so a formula is never altered. The proof mode does
not rewrite by default, because a wrong change to a quantifier order or an
inequality direction changes a theorem; it routes to the judge, and the fix loop
is opt-in.

A clean gate or a passing receipt means the prose was screened. The mathematics
is for a referee or a proof assistant: a clear proof can still be false.

## The editor layer

With a model, the editor adds judgment and rewriting:

- `judge` reads the judgment-level failures a regex misses: a fluent paragraph
  empty of facts a reader could restate, vague abstraction, hedging that avoids a
  position, a weak verb carrying the meaning. It reports.
- `fix` rewrites to a plain, skilled standard, checks protected spans, and
  re-runs the detector. Remaining findings stay visible.
- `polish` runs a monotonic loop that accepts a pass when the gate stays clean
  and every assessed quality score holds or rises. Missing scores leave
  host-submitted quality unassessed; the model loop keeps the best prior text.
  These checks decide acceptance. Read the result to judge whether the meaning
  held and the writing improved.

Every result identifies its backend, model and failed attempts. The available
backends are `host`, `sampling`, `anthropic`, `claude-cli`, `openai`, `ollama`
and the local `none`, with `auto` choosing for the current surface.

In an MCP session, automatic selection uses sampling only if the client
advertised that capability. Otherwise it returns an edit plan to the calling
model before trying a separately billed backend. The host protocol also works
through `articulate plan` and `articulate submit` without MCP sampling support.
The plan supplies local findings and their reasons, rewrite or judge
instructions, masked text, protected spans and a plan ID bound to the source,
profile and ruleset. The caller submits its rewrite with that ID and the
original text. Articulate restores masks, checks the guard, reports gate and
per-rule changes, and returns a receipt with `backend: host`. A caller-supplied
model name records attribution; it does not authenticate the model.

The guard checks numbers, URLs and link targets, citations, code, math and quoted
text. A refused span keeps its original wording and gets a reason. The guard
applies to model and deterministic edits. Protected spans cannot establish
semantic equivalence: a rewrite can retain every number and still change a claim.

An edit can allow named kinds of protected change, such as a number it is meant
to update (`--allow-change number`, or `allow_change` on the MCP `fix`,
`polish` and `edit_plan` tools). An allowed change is reported in
`allowed_changes` in the result and the editor receipt. The plan binds the allowed kinds (plan schema
`articulate/edit-plan/v3`), so a submission keeps to them, and v1 and v2 plans
still verify. Disclosure lines, an added first-person sentence, HTML and math
are always protected.

A change report (`--explain` on `fix`, `polish` and `submit`, or `explain` on
the MCP `fix`, `polish` and `edit_submit` tools) pairs each changed sentence
with its original and lists the findings it cleared, kept or added, the
paragraphs the guard kept and why, and every allowed change. It shows what the
checker saw in each sentence; it does not show why the editor made a change or
that the meaning held.

With no model reachable, `none` makes conservative mechanical edits and reports
what remains. It can replace clause dashes and remove safe filler or extra
spaces; it leaves protected content alone. Its `judge` returns local findings
and reasons, with model scores left empty. This result works offline. A
successful call can still contain blocked findings or refused edits; inspect the
gate and refusal list.

Plain CLI automatic selection tries configured Anthropic, the Claude CLI,
configured OpenAI-compatible endpoints, Ollama and `none` in order. Ollama
uses the models you have installed. Configuration and the model
preference order are in the [CLI reference](cli.md#backend-configuration).

Anthropic and the Claude CLI send text to their provider. OpenAI-compatible and
Ollama backends send it to the configured endpoint, which can be remote. Host
editing and sampling follow the host's data handling policy. `none` stays local.
`ARTICULATE_LOCAL_ONLY=1` limits editing to loopback Ollama and `none`, and
refuses other editor backends before a connection. Plans and edit results contain source text;
they are separate from content-free detector audit receipts.

The document is treated strictly as data. A trust boundary is appended to every
model call, so a directive embedded in the text (a line that says to ignore the
standard or to reply approved) is edited as content. The rewrite optimizes
writing quality for the reader.

## The process record

`articulate process` keeps a local log of your own process in
`.articulate/process/` beside the document, with a `.gitignore` of its own.
Recording starts when you run a command.

- A draft entry holds a salted commitment to the text, its sequence and the day.
  Word counts, lines changed, times and snapshots are opt-in per log and stay out
  of a default export.
- Notes, sources, declared tool assistance (generated, drafted, edited,
  translated), reviews by role, anchors to a git commit or a timestamp token, and
  a continuation entry for a log that broke.
- How you put words down (dictation, a screen reader, switch access, drafting in
  another language) goes to a private file outside the log. An export or
  statement includes it when you name it, and the sequence numbers skip it.
- `export` writes `<document>.process-summary.json`: two labelled document hashes,
  the entry sequence, a C2PA-shaped actions list with IPTC digital source types,
  your disclosure statement and the limits of what the summary shows. Entry
  hashes stay in the log, which keeps withheld fields private.
  `--reveal N` attaches draft N's text and salt.
- `verify` on a log reports `intact` (exit 0), `broken` (exit 1) or `missing`
  (exit 3). A log records what the writer chose to log; `verify`, `export` and
  `disclose` each print that limits line. On a summary (found by its schema) it checks the chain state the
  summary records and each reveal.
- `continue` starts a new log after a broken one. The new first entry names the
  last good entry and carries every recorded assistance entry forward.
- `fix` and `polish` add their own assistance entry when the document has a log,
  including when a later pass fails.
- `--track` lets git see the log and still keeps salts, the diff cache, snapshots
  and input methods out of it.

## Disclosure statements

`articulate disclose` writes a statement from the log: assistance with the task
verb as recorded, and CRediT credit for people only. It refuses when the log is
missing or broken. It refuses a claim that matches its list of no-tool phrases
("No AI was used", "written without any AI tools") when the log records
assistance; a paraphrase outside the list passes, so the Assistance section is
the record. It refuses to leave out a recorded assistance entry. An author whose
whole name is a product name ("Claude", "GPT-4o") is refused unless the entry
says `"type": "person"`; a person who shares a word with a product, such as
Claude Shannon or Ai Weiwei, passes. A `pip` template writes `Assisted-by:`
commit-trailer lines for a model, and co-author trailers for people.

## The review desk

`articulate desk` prepares the questions a reviewer should ask. Inside the
document it asks about numbers with a source missing nearby, appeals to unnamed
authority, sections or statements a venue asks for, and text hidden from a
reader: white or zero-size text, `display:none`, `visibility:hidden`, zero
opacity, zero-width characters inside Latin text, bidirectional controls and
Unicode tag characters, whose hidden sentence it spells out. Across the field it asks five fixed questions about what the work
adds, and quotes the authors' own claims beside them. The output is questions
and quotes; scores, verdicts and rankings are left to the reviewer, and process
records stay unread.
`--author` asks the same questions before submission.

## Re-derivable receipts

A receipt records a detection result together with the exact text hash and a
fingerprint of the whole ruleset. Anyone replays it: recompute the findings on
the same text under the same ruleset and confirm they match, with no network and
no trust in whoever issued it first. The verdict uses a closed set of three:

- `Match`: same text, same ruleset, identical findings and gate.
- `Drift`: same text and ruleset, but the re-derived findings differ.
- `Unverifiable`: the ruleset moved, the text hash mismatches, or the text is
  below the signal floor, so the replay stops short of a comparison.

The receipt certifies that anyone can recompute it. Trust rests on that replay,
so the issuer's identity carries no weight.

## Per-paragraph findings

`--spans` scores each paragraph on its own and reports its line range, so a single
paragraph dense with devices in an otherwise clean document is flagged in place, and one
aggregate score cannot smear across the whole file. A per-span receipt records the
per-block verdicts, each with its own text hash.

## Sub-threshold calibration

Below a 30-word floor there are too few words to call a text clean, so a
device-clean short text reads `unverifiable` and the receipt abstains rather
than emit a confident verdict on noise. A banned device is unambiguous at any
length, so a short text with a device still reads `flagged`.

## The content-free audit receipt

For a team that must retain a record without keeping the sensitive text, a
content-free receipt drops the matched substring and the exact offsets, and keeps
only which rule fired, its tier and category, and the line. It still replays to
`Match`, and `verify` rejects a mislabeled or a smuggling receipt. The `articulate
audit` command queries a directory of committed receipts locally, and with
`--reverify` it re-checks that each still holds against its source, failing the
gate only when a source drifted or changed since it was screened.

A content-free record still names which rules fired and on which line. For a
closed-vocabulary rule, that narrows the flagged word to the rule's small public
candidate set. Read [Boundaries](boundaries.md) before you rely on it.

## Binary inputs fail closed

A binary or an unsupported document (a `.docx`, a PDF, an image) is refused with
an explicit reason, so a lossy decode can never come back as a clean scan.
Convert it to text or Markdown first. A UTF-8 document in another language is
screened; the patterns are English literals, so expect few findings on it.

## Surfaces

The same detection reaches you through several surfaces:

- CLI: `check`, `score`, `receipt`, `verify`, `audit`, `modes`, `process`,
  `disclose`, `desk`, `plan`, `submit`, `judge`, `fix` and `polish`, plus the
  `house`, `voice`, `corpus`, `titles`, `interview` and `restructure` commands.
- LSP server: inline squiggles in VS Code, JetBrains through LSP4IJ, and Neovim.
  It runs on the Python standard library.
- SARIF: `check --sarif` for GitHub code scanning, Azure DevOps, and reviewdog.
- MCP server: the detector and editor as tools for an agent.
- GitHub Action and a pre-commit hook, wired to gate a change and to re-verify
  committed receipts.
- A VS Code client in `editors/vscode/` and a JetBrains note in
  `editors/jetbrains/`.

## The benchmark

`articulate.bench` is a regression check. It runs the detector over a small
corpus of nine files and fails when a file stops raising, or starts raising, what
it raised before. The exit code is the number of changed files, so a checker can
gate on it. Its counts are no measure of detection.

The measure against ground truth is `scripts/provenance_eval.py` on the
[known-provenance corpus](../corpus/provenance/README.md): all 84 AI texts
flagged, and 57 of 75 human texts flagged as well.
