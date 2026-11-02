# Recall index

Find what was said in months of agent sessions without a model reading them. The recall index distills session transcripts (Claude Code JSONL) into one SQLite file in a single streaming pass per file, with no model calls, then answers a question with a few short hits and a pointer back to the exact source line. When the answer is not there, it says "not found".

```sh
python -m harness.recall_index build --db recall.sqlite --transcripts ~/.claude/projects/<project>
python -m harness.recall_index query --db recall.sqlite "where does BuildQL live"
python -m harness.recall_index show "<pointer from a hit>"
python -m harness.recall_index cards --db recall.sqlite build-universe
python -m harness.recall_index stats --db recall.sqlite
```

Run `build` again at any time: it reads only bytes appended since the last run. Reference notes (Markdown or text) go in with `--refs FILE ...` or `--refs-list FILE`, under their own scope, marked for internal use.

## How it works

1. **Split.** Each record becomes typed units: author message, assistant prose (per paragraph), tool call (name plus command or path), tool result (ok or error only, joined to its call), relay (task notifications, subagent briefs) and compaction summary. Attachments, hook context, system reminders and tool-result bodies are dropped. Lines over 4 KB are classified from their head and tail before any parse, so a 10 MB tool output costs almost nothing.
2. **Gate.** Secrets and personal content become stubs with a reason and a pointer, contact details are redacted, and a reply that a safety classifier stopped is never stored.
3. **Score.** Fixed, inspectable weights in `features.py`: KEEP THIS tags, author rulings in quotes, decisions and verdicts, finding numbers, measurements, PR and commit references, paths, versions and names.
4. **Collapse.** A line seen in 5 or more sessions is kept only where it first appeared. Near-duplicate units collapse by 64-bit SimHash (four 16-bit bands, Hamming distance 3 or less).
5. **Index.** FTS5 over live units, entity postings, and one card per ruling or decision with its verbatim quote. Ids are content addresses, identical across machines.
6. **Recall.** BM25 candidates pass an IDF coverage gate: the share of the query's information present in the hit must reach 0.6. A term the index never saw carries the most weight, so a question about something absent returns "not found" instead of a near miss.

## Measured

One build over 216 transcripts on a desktop CPU: 5.39 GB read in 150 seconds at 83 MB peak memory; 173,283 units staged, 128,100 live after 19,370 boilerplate and 25,813 near-duplicate units collapsed; 2,891 cards; 1,270 units skipped by the gates; index 355 MB. A rerun with nothing new took 0.1 seconds. On 42 questions with known answers, written and hashed before the code existed, it found 19 at k = 5, where the best existing tool found 10 and a ripgrep baseline 4, at about 290 tokens per answer. On 6 questions with no answer it said "not found" 5 times; the existing tools never did.

## Limits

- Lexical recall: a question phrased in words the record never used can miss. The coverage gate trades some recall for a reliable "not found".
- The personal-content gate is a fixed pattern list, so it can miss phrasing it does not know and can skip work text that resembles it.
- Subagent transcripts in subfolders are not read yet.
