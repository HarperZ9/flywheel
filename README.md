# Flywheel Desktop

The native desktop surface for [Flywheel](https://github.com/HarperZ9/flywheel):
one window over the whole platform. Route any model, watch the verified loop,
read the receipts. No browser, no terminal.

## What you get

- **Lanes** — the flagship tool family (gather, crucible, index, forum, learn,
  telos, local-model) with live health. Probing spawns each tool's own MCP
  server and asks it directly; the verdict shown is the tool's answer.
- **World** — the projected, root-hashed state. Recomputed on every read:
  tamper any cataloged receipt and the hash moves.
- **Receipts** — the ledger of re-checkable artifacts: the in-repo catalog,
  re-hashed on every read, and the proof envelopes written when verified work
  is accepted. No receipt, no accept.
- **Companion** — ask once, the seat answers from the cheapest honest source.
  Verified and cached answers carry a verified chip; agreement without proof
  is labeled consensus; hard prompts escalate with the failed local attempt on
  record. The chip never lies.
- **Endpoints** — the universal router roster. Local tiers are probed live;
  hosted providers show credential presence only (the env var name, never a
  value); the scoreboard shows observed routing outcomes, not promises.

## Run it

Install the engine and start it once:

```
pip install flywheel
flywheel up
```

Then run the app:

```
flutter run -d windows --release
```

If the engine is offline the app says so and can start it for you.

## Design

Two typefaces (Hanken Grotesk and Conso), bundled. Color only ever means a
verdict: verified green, drift iris, unverifiable gray. Ceramic light and
near-black dark themes, both AA. Cards are ground tints with a hairline
border; there is no glass and no decorative color anywhere.

## Build and test

```
flutter analyze
flutter test
flutter build windows --release
```

## Honest boundaries

The app displays what the engine can prove and labels what it cannot. Model
answers that fail verification are shown as escalations, not dressed up as
results. Credentials are never collected, stored, or displayed by this app.
