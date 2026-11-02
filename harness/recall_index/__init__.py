"""Recall index: a deterministic distiller for agent session transcripts.

One streaming pass per transcript file, no model calls, CPU only, small
memory. Each JSONL record is split by kind (author, assistant, tool_call,
tool_result, relay); hook-injected context, system reminders, attachments
and tool-result bodies are dropped. What remains is scored on explicit
features (author rulings, KEEP THIS tags, decisions and verdicts, finding
numbers, PR and commit references, paths, named entities), collapsed for
near-duplicates with SimHash, and written to one SQLite file with FTS5.

Recall is a lookup in that index plus a pointer read back into the source
transcript at a byte offset. Later runs read only the bytes appended after
the last recorded offset.

Privacy and safety gates run before anything is stored: secrets and
personal content become skipped stubs with a pointer and a reason, and a
reply that a safety classifier stopped is never stored.
"""

SCHEMA_VERSION = 1
