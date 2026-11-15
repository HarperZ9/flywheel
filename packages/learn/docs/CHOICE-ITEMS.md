# Choice items

A choice item is a short recall question with one keyed answer. Each wrong choice can name the misconception that would lead a reader to pick it. When the reader picks a wrong choice, the tutor says which misconception that choice matches. It does not say which choice was right.

## Format

One item, schema `learn-choice/1`:

```json
{
  "id": "rinv-1",
  "objective": "receipt-vs-verdict",
  "prompt": "A rerun gives the same hash. What does that show?",
  "choices": [
    { "id": "same", "text": "The same bytes came out" },
    { "id": "right", "text": "The output is right" }
  ],
  "answer": "same",
  "misconceptions": {
    "right": { "leaf": "misrecruited.receipt_as_verdict", "note": "A matching hash shows the bytes are the same. Whether they are right needs a criterion." }
  },
  "source": { "ref": "no-receipt-no-accept.html#4-the-loop-walked-end-to-end", "quote": "Same bytes. Not yet right bytes." }
}
```

A set of items, schema `learn-items/1`, is `{ "schema": "learn-items/1", "topic": "...", "items": [ ... ] }`. Item ids are unique within a set.

## Rules

- Two to six choices, each with an id and text. `answer` is one of the choice ids.
- A misconception is keyed on a wrong choice id. Its `leaf` uses the same top levels as the arithmetic tree in `MISCONCEPTION-DIAGNOSIS.md`: `missing`, `misrecruited` or `slip`, then a dot and a lowercase name. Its `note` says what the misconception gets wrong.
- The keyed answer cannot carry a misconception; `validateItem()` rejects that.
- A note should explain the mistake without quoting the keyed choice. The tutor cannot check this; the item's author does.

## Functions

| Function | Returns |
|---|---|
| `validateItem(item)`, `validateItemSet(set)` | the input, or an error naming the first problem |
| `publicItem(item)` | the id, objective, prompt and choices: what a page shows before the attempt |
| `diagnoseChoice(item, choiceId)` | `{ correct, leaf, top, note, path }`; never the keyed answer |

A wrong choice with no named misconception reads `missing.unexplained`. No choice reads `missing.no_attempt`. Record the attempt with `recordAttempt(session, { ..., misconception: leaf })` and `misconceptions(session)` counts it.

## In a browser

`@harperz9/learn/browser` (`src/browser.mjs`) exports these functions together with the session, mastery and spaced-review functions. It has no Node built-ins, so a page can import it as an ES module. Receipts, the session store, the CLI and the MCP server stay Node-only.

## Limits

The diagnosis is only as good as the item's author. It reports the misconception the author attached to a choice. It does not infer one, and it does not check that the note is true.
