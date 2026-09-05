# A native surface for agents to operate a workstation

Status: plan. Nothing here is built. Written 2026-09-05.
Sibling: `2026-09-05-neutral-agent-surface-api.md` covers the market assessment
and the platform-API adapter. This document covers the workstation itself.

## What this has to beat

The default way an agent operates a workstation today is a screenshot, a vision
model, and a click at a coordinate. That path pays image tokens on every step,
breaks when resolution or theme or scroll position changes, and leaves no record
of what was done. It is also the only path most harnesses offer, which is why it
gets used for work a single text call would have finished.

The goal is a surface where the expensive path is the last resort rather than
the entry point.

## What is already built here

Read from code on 2026-09-05, not from README claims.

**telos** carries the native control.

- `tools/uia.ps1` (166 lines) drives Windows UI Automation with verbs `windows`,
  `tree`, `invoke`, `setvalue`, `focus`. It acts through UIA patterns
  (InvokePattern, ValuePattern, SetFocus), which dispatch into the target
  process without moving the mouse or keyboard. JSON in, JSON out. It wrote
  that JSON on the console codepage until 2026-09-05, so any non-ASCII
  control name came back corrupted and the Node caller threw. Fixed in
  telos#38.
- `tools/device.ps1` (59 lines) is the OS primitive: `exec`, `read`, `write`,
  `ls`, with a receipt recording the command and its exit code.
- `tools/captcha-solve.py` also exists. This design does not call it. See the
  exclusions below.

**accountable-surface** carries the accountability contract.

- `effector.py` defines a frozen `Plan` (action kind, target, content hash,
  reversibility, prior existence, content-addressed digest), a `Verdict`, and
  `RefusedActuation`. An effector stays inert until a gate allows that exact
  plan, then re-perceives to verify what changed.
- `grant.py` separates two permissions that usually get conflated:
  `allowed_perceptions` is what the operator lets an agent look at, and the
  closed action-authorization schema is what it may do.
- `journal_chain.py` hashes each entry against the one before it, so an edited
  entry breaks its own hash and a deleted or reordered entry breaks the linkage.
- `world/sight.py` renders a screen as an ASCII glyph grid plus a spatial colour
  map plus a perceptual hash, so a text model perceives a display without paying
  image tokens.
- `world/screen.py` skips a byte-identical frame instead of re-witnessing it.
- `world/structure.py` reads contours and reports a re-derivable ghash.
- `world/pilot.py` runs perceive, propose one action, gate, act, verify, witness,
  and is model-agnostic.
- `browser_effector.py` and `web_effector.py` sit on a Playwright driver and an
  HTTP driver.

**gather** carries the provenance discipline. `method.py` classifies every
retrieval as DIRECT or DERIVED and enforces the classification against the
derivation chain, so an item cannot claim a direct read while carrying inputs.
`ocr.py`, `pdf.py`, `browser_evidence.py`, `credentials.py`, and `cache.py` fill
in the retrieval rungs.

**Windows-MCP**, a third-party server already connected to this session, offers
App, Click, Type, Snapshot, Scrape, Registry, PowerShell, FileSystem, Clipboard,
and Shortcut. Useful as a reference and a fallback. It is not ours.

The pieces exist. Missing: one entry point, a shared verb vocabulary, a
cost-ordered escalation between the pieces, and a cached map of what worked.

## The technique space

The operator asked to visit the techniques rather than pick one early. Here they
are, ordered by cost per step.

### Rung 0: the surface already answers in text

- **Local CLI.** `git`, `ffmpeg`, `yt-dlp`, `winget`, `gh`. Structured output,
  exit codes, no UI at all. Often the cheapest path available, and routinely
  skipped in favour of driving the app's window.
- **Platform HTTP API.** The adapter covered in the sibling plan.
- **OS automation APIs.** COM on Windows reaches Office, Explorer, and much of
  the shell. macOS has AppleScript and JXA. Linux has D-Bus. These are scripting
  interfaces the vendor supports, so they survive updates.
- **App plugin or socket APIs.** The VS Code extension host, the OBS websocket,
  a Discord gateway bot the operator installed. Where a vendor publishes a
  control channel, use it.
- **URI schemes and deep links.** `vscode://`, `obsidian://`, `spotify:`. One
  call replaces a click sequence whose only purpose was navigation.
- **Config and state files.** Many applications keep state in JSON or SQLite. A
  read answers a question with no UI involved. Writing while the app runs is
  usually unsafe, so treat this as a read-only rung by default.

### Rung 1: structured accessibility

- **Windows UI Automation.** What `uia.ps1` already does. The control tree gives
  names, roles, automation ids, and patterns. Invoking a pattern does not move
  the pointer, so an agent working here does not fight the human for the input
  device.
- **macOS AX API and Linux AT-SPI.** The same idea on the other two platforms.
- **Chrome DevTools Protocol.** DOM plus accessibility tree, which covers every
  Electron application as well as the browser. That is a large share of a modern
  desktop.

Text-only, small payloads, high reliability wherever the tree is honest.

### Rung 2: derived structure from pixels

- **The glyph grid and colour map** from `world/sight.py`, which a model reads
  as text.
- **Contours** from `world/structure.py` for layout and shape.
- **OCR** from gather for text baked into an image.
- **Template and icon matching** for a control with no accessible name.

This rung exists for canvas applications, games, remote desktop sessions, and
anything whose accessibility tree is thin or misleading.

### Rung 3: raw vision and coordinates

A screenshot to a vision model and a click at a point. This costs the most per
step and breaks whenever the layout shifts. It stays in the ladder because some
surfaces offer nothing else.

### Cross-cutting channels

These are the workarounds worth naming, because several collapse a whole UI
sequence into one call.

- **Command palettes.** A modern editor's palette accepts a command name. That
  is a verb vocabulary the application already publishes, reachable with a
  keystroke and a string, and usually stabler than the menu tree.
- **Keyboard shortcuts.** They survive redesigns that rename controls.
- **Clipboard as a typed bus.** Read a selection out, push a payload in, neither
  requiring a control to be located.
- **Filesystem as a bus.** Watch folders, export and import, drop a file where
  the application already looks.
- **Window management as a precondition.** Focus and geometry are setup for an
  action rather than the action itself, and treating them that way keeps the
  plan honest about what actually changed.
- **Teach by demonstration.** Record a sequence once with the operator driving,
  replay it deterministically afterward, and re-verify each replay so a drifted
  UI fails loudly instead of clicking the wrong thing.
- **Print to PDF.** A universal export for an application that publishes no
  export verb.
- **Queue and schedule.** Where a surface meters, the surface should hold the
  work rather than let the caller burn the quota.

### Excluded

CAPTCHA solving, residential proxy rotation, fingerprint spoofing, and self-bot
tokens. These aim at making automated traffic pass as human, which is precisely
what the edge is now built to detect, and it is not work I will extend.

## Architecture

1. **A closed verb vocabulary.** Small and shared: `list`, `read`, `search`,
   `open`, `focus`, `set`, `invoke`, `select`, `export`, `wait`, `close`. A
   surface pack declares which verbs it serves and on which rung.
2. **A surface map cache.** First contact walks the tree once and stores verb to
   selector, keyed by application identity and version. Later calls skip
   discovery. Most of the token saving comes from here rather than from any
   single rung.
3. **Cost-ordered escalation with recorded provenance.** Try the lowest rung
   that declares the verb, escalate on failure, record which rung answered. This
   copies gather's `method.py` directly: a rung ladder, plus a consistency rule
   so a result cannot claim a rung it did not use.
4. **Plan, gate, act, verify.** Reuse `effector.py`'s `Plan` and
   `RefusedActuation`, `grant.py`'s split between perception and action
   permission, and `journal_chain.py` for the record.
5. **One vocabulary, two transports.** Local stdio MCP for agents on the
   workstation, and the same verbs over bulletin for a remote agent whose
   ed25519 identity lands in the receipt.
6. **Refusal is an answer.** When no rung can serve a verb, the reply
   says unavailable and lists the rungs tried. A surface that quietly falls back
   to guessing is worse than one that stops.

## What separates this from computer use

Computer use is rung 3 with no memory. This starts at rung 0, remembers which
rung worked for that application at that version, and returns a receipt a third
party can check. The escalation policy and the cache are the mechanism under
test.

## Measurement

The claim to test is the operator's own: token efficiency. Measure with crucible
on a fixed task set, against a screenshot-driven baseline at equal correctness.

- Median tokens per completed task, with an interval.
- Rung distribution: what fraction of tasks finish without leaving rung 0 or 1.
- Cache hit rate on the second run of the same task.
- Breakage rate after an application update.

Correctness gates everything. A cheaper path that returns the wrong answer is
not a saving, so every task needs a checkable success condition written before
the run.

## Phases

**Phase 0.** Vocabulary, rung ladder, and the provenance consistency rule, as a
spec with tests and no I/O. Cheap, and it settles the interface before any
adapter hardens around a bad one.

**Phase 1.** A Windows pack over `uia.ps1` covering rungs 0 and 1 for three
verbs against one application with a stable tree. The surface map cache ships
here, since it is the mechanism under test.

**Phase 2.** The measurement harness. Ten tasks, ladder against baseline,
published with intervals and the rung distribution. This is the kill point.

**Phase 3.** Gate, journal, and receipt on every action, with the refusal path
under test.

**Phase 4.** Remote reach through bulletin, caller identity in the receipt.

**Phase 5.** A second pack, the platform-API adapter from the sibling plan, to
show the vocabulary survives a surface that is not a desktop.

Kill criterion at Phase 2: if the ladder fails to beat the screenshot baseline
on median tokens at equal correctness by a wide margin, the premise is wrong and
the work stops there.

## Risks and honest limits

- `tree` caps at 300 elements and the cap bites immediately. Measured
  2026-09-05: Slack returned 298, Discord 300, ChatGPT 300. Three of four
  candidate targets are truncated before any search begins, so paging is a
  prerequisite.
- `uia.ps1` locates an element by a full descendant scan with substring
  matching. AutomationId-first lookup was the proposed fix, and the same
  measurement shows it half works: Slack carries 50 AutomationIds across 298
  elements, ChatGPT 16, Discord 2. Name matching stays load-bearing.
- An earlier version of this section said Electron and Qt trees are usually
  thin or misleading. That claim is withdrawn. Four Electron applications
  measured 2026-09-05 on the target workstation: Claude 168 elements with 150
  named and 68 buttons, Slack 298 with 233 named, Discord 300 with 299 named,
  ChatGPT 300 with 293 named and 186 buttons. Qt is untested and stays unknown.
- A cached surface map goes stale when the application updates. It needs a
  version key and a cheap validation probe on load.
- Rung 3 stays necessary for canvas applications and games. The ladder shrinks
  its share without removing it.
- Demand is unvalidated, exactly as in the sibling plan. Treat the whole thing
  as exploration until someone asks for it.

## Decisions

Answered 2026-09-05.

1. **First target: Slack.** The draft asked for a stable Win32 tree. Nine top
   level windows were open on the workstation this is written for, and none of
   them was classic Win32: five Chromium applications and four consoles. Slack
   carries the best AutomationId coverage of the Electron candidates, offers 63
   buttons and 25 hyperlinks for `invoke`, and runs on Chromium, so `cdp.mjs`
   supplies a second rung 1 path. Discord is the target to avoid, at 2
   AutomationIds across 300 elements.
2. **Local transport: telos through Phase 2, split afterward.** telos already
   owns `uia.ps1`, `device.ps1`, `cdp.mjs`, and `demo/native-control/`. A
   separate server would import from telos or copy it, and it cannot move the
   Phase 2 number that decides whether the premise survives. Splitting later is
   cheap because the vocabulary is closed by design. The cost of waiting is
   context hygiene: workstation verbs on telos load wherever telos loads. Split
   early if that bites before Phase 2.
3. **Teach by demonstration: deferred to Phase 3.** It needs a recorder, a
   deterministic replayer, and a drift check that fails loudly. None of that
   moves the Phase 2 measurement, and building it first spends the effort
   before the premise is tested.
