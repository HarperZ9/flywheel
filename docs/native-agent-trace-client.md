# Native private trace reader

The live operation result offers a private trace dialog when the authenticated
operation carries the metadata projection defined in
[the trace contract](native-agent-trace-contract.md). Opening the dialog shows
metadata; reading each original record requires an explicit read action.
Reads use the existing authenticated gateway transport. Retry repeats only GET,
never the operation submission. Closing the dialog cancels its pending request
and releases its in-memory records. It writes no private content to history,
logs, files, or an export destination.

The client binds records to the requested operation, Journey, and trace. The
returned owner must derive the same trace reference; the gateway enforces the
authenticated owner. SHA-256 is calculated over the supplied original canonical
bytes, including Python float spelling and Unicode. Strict parsing rejects
duplicate keys and requires the decoded bytes to match the displayed record.
Each loaded sequence must continue the prior hash. A complete read must reach
the advertised count and head. A running projection captures an accepted prefix;
later records are not silently added to that captured read.

The reader enforces a 30-second total request deadline, 36 MiB response bound,
8 MiB canonical record bound, 32 MiB aggregate trace bound, and 2048-record bound.
It loads one page at a time. The native decoder also bounds a page to 250,000
JSON values and integers to 4300 digits. A record beyond these reader limits
remains retained on the gateway and is shown as unavailable in this client,
without truncation. Large original records use navigable text windows;
the complete original text is retained without ellipses or hidden truncation.
Unavailable records, omitted public content, partial execution, and partial
reading have separate labels. Matching hashes do not establish semantic truth,
source truth, an independently verified inner ledger, or recovery of output
discarded before record insertion.

Synthetic shared contract fixtures exercise Python floats and Unicode. Dart
controls cover altered hashes and bindings, duplicate JSON keys, prior-chain
breaks, growing running prefixes, read retry, bounds, disposal, and the opt-in
viewer. No test reads real user history. The fixture source is the backend trace
boundary; backend and client changes must ship together.
