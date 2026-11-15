# blocks - the authored block set

This directory is canon's authored block set: the canonical source of record for
the operator's standing personality blocks. Each file is one `canon.record/v1`
record of kind `personality-block`, the same envelope the engine validates,
layers, and renders. The set is the pool that `resolve_blocks` resolves and
`render_surface` projects onto a scope before splicing it into a host instruction
file.

## What a block file is
One JSON file, one record. The shape matches `tests/fixtures/records/personality_block.json`:

- `canon_schema` is `canon.record/v1`.
- `kind` is `personality-block`.
- `id` is a stable kebab-case slug, unique within a scope. The filename is the id
  plus `.json`.
- `scope` is `global` or `workspace`. A `global` block renders into every
  surface; a `workspace` block overlays the global set on a workspace render and
  can override a global block that shares its id.
- `data` carries a non-empty `title` and a non-empty `body`.
- `provenance` carries `harness` and a lowercase 64-hex `source_hash`, plus a
  clock-free `create_ord` used for deterministic ordering. An authored block sets
  `harness` to `author` and points `source_hash` at the sha256 of the text of
  record the block distills.
- `temporal` carries `valid_until` and `supersedes`, both null for a live block.

## Authoring a block
1. Write the record as a JSON file named for its id.
2. Validate it against the engine's own rules before committing:

   ```python
   import json, pathlib
   from canon.schema import Record
   from canon.validator import validate_record
   from canon.layering import resolve_blocks

   rec = Record.from_dict(json.loads(pathlib.Path("blocks/<id>.json").read_text("utf-8")))
   assert validate_record(rec) == []                 # no semantic errors
   assert rec.to_dict() == json.loads(pathlib.Path("blocks/<id>.json").read_text("utf-8"))
   assert rec in resolve_blocks([rec], rec.scope)     # resolves into its scope
   ```

3. Run the suite: `python -m pytest`.

A block set is data the renderer consumes, so keep it public-clean: no local
paths, no secrets, no em-dashes, and prose that reads for the surface it lands on.

## Current blocks
- `evidence-insight-and-useful-work.json` - the standing evidence, insight, and
  useful-work rule. Scope `global`, so it reaches every rendered surface. It is
  the canonical home for the rule that currently lives hand-synced across the
  instruction files; the renderer is what will keep those copies in step once
  canon runs live on them.
