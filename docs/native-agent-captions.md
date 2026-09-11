# Private native captions

`AgentCaptionPanel(reader: reader, projection: projection, onClose: callback)`
is an opt-in native panel for accepted operation trace metadata. The host keeps
one `GatewayAgentTrace` reader backed by its authenticated gateway client and
updates the projection as accepted operation metadata arrives. A changed reader,
operation, Journey or trace closes the old read and requires a fresh opt-in.
The attachment belongs beside the native operation UI, outside Rowan artwork
and animation controls. This component does not attach itself to those surfaces.

The reader follows the existing private GET contract in
[native-agent-trace-contract.md](native-agent-trace-contract.md). It reads each
sequence once as metadata advances and checks the original record digest,
owner-derived trace binding, operation, Journey, prior hash and advertised heads.
Ownership is enforced by the authenticated gateway. An incomplete prefix is
labelled partial until the advertised head is reached. Hash agreement establishes
recorded bytes and bindings, not semantic truth or independent source truth.
The existing bounds remain: 2,048 records, 8 MiB per canonical record, 32 MiB per
trace and 36 MiB per response. No backend or public IPC content is added.

Current caption sources are full `ledger.content` assistant output and tool
records, private `model_inference` lifecycle records, reported budget progress,
and retained `result.final` output. The short assistant and tool progress
mirrors are omitted to avoid duplicate captions. Tool calls in this loop are
recorded after execution, so the panel does not claim the tool is currently
running. Inference lifecycle captions are derived only from
`flywheel.gateway-agent-inference/v1` metadata with bounded ordinal, binding
hash, endpoint, model, phase, timestamp, elapsed time and failure reason fields;
they summarize provider-call lifecycle, not hidden reasoning. Unsupported
records are counted separately from mapped captions. Original canonical records
remain available for mapped captions, with sequence, owner, hashes and exact
retained material; the private trace viewer remains the route to unmapped
records.

Provider reasoning, provider summaries and generated summaries have separate
reserved kinds. They are not inferred from assistant text, inference lifecycle
metadata or field names. The current native backend supplies provider-call
lifecycle records but no distinct supported provider-summary channel, and the
panel says summaries are unavailable. Supported Anthropic thinking output is a
provider summary, not raw internal chain of thought; a future backend
integration needs an explicit request option and authenticated trace fixtures
before enabling its decoder. Opaque signatures and redacted data are never
interpreted as caption text. See [Anthropic thinking documentation](https://platform.claude.com/docs/en/build-with-claude/thinking).

Records are ordered by verified trace sequence. The shown UTC receipt timestamp
is observed locally when a record is read; it is not an inference start, provider
timestamp, or execution duration. Old records have no event timestamp. The panel
does not invent token rates or infer hidden thoughts.

Pause follow controls caption scrolling only. Private reads and the task can
continue; retry repeats a GET for the same sequence without resubmitting an
action. Dragging the caption list pauses following. Text size ranges from 14 to
28 logical pixels and respects platform text scaling. Reduced motion and
accessible navigation use immediate scrolling. Long captions show an explicit
excerpt with a windowed original-record view.

Close aborts the pending read, clears retained text and original-record views,
and rejects late completions. Disposal does the same. No caption content is
logged, persisted, spoken, copied to a public board or shared automatically.
This component has no share or speech callback; any future sharing attachment
must use the application's existing explicit reviewed sharing flow.

Synthetic tests cover authentic record-byte parsing, replacement heads, broken
chains, metadata regression, retry, late completion, pause-follow, close and
readable reduced-motion layout. They use no real user history. The fixtures
exercise transport and display claims, not model quality or provider behavior.
