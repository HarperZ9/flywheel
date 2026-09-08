# Flywheel 0.6.0

This update connects imported context to an agent run, brings background
repository mapping into Projects, and retains usage from local model calls.

## Continue an imported task with an agent

In Projects, preview a supported local continuation source, then choose
**Continue with agent**. Flywheel starts the Evidence Journey and supplies
the agent with the selected goal, files, and workspace.
Execution still requires the normal operation approval.

The handoff binds the preview to the Journey created from it. An unrelated
Journey cannot reuse that context, and a preview alone does not authorize a run.
Source changes and invalid bindings produce a specific error for the user.
This continues portable context; provider-native session resume remains limited
to supported adapters. Credentials stay outside the context handoff.

## Map a workspace without holding the request open

Projects separates the repository summary from a durable workspace-map job.
The job reports its phase and repository progress. Users can cancel it, return
to the project, retrieve a completed result, or resume a recoverable job.
Switching projects detaches the view without cancelling the earlier job;
a late response from that project cannot replace the current selection.
Completed results are snapshots. After changing source files, choose
**Update workspace map** to start a fresh job and refresh the summary.

This workflow requires Index 2.12 or newer with router-job support. Index is a
separate engine installation. Missing or incompatible installations report
unavailability. The summary has a bounded timeout; full mapping runs in the
background rather than inheriting the earlier request timeout.

Repository coverage and document selection are separate: the default context
selection limit is 500 documents. A completed job does not imply that every
document was selected, or that the resulting context is semantically complete.
Background execution improves observability and recovery; it does not by itself
establish faster mapping.

## Preserve local usage when a task fails

Nonstreaming Ollama calls retain supported native token counts and durations.
Benchmark traces identify each attempted inner call, including calls that fail
before returning telemetry. Missing fields remain unknown. An incomplete trace
cannot become a complete aggregate by dropping a failed call.

Malformed task output can retain verified usage while remaining a failed task.
Native timing fields keep their original nanosecond units, and these counts do
not establish cost, answer quality, or an accuracy improvement.

## Recover a busy operation snapshot

The operation reader also handles a busy store encountered while loading the
Journey projection. It uses the existing bounded retry and continues to report
unrelated storage failures as errors.

## Distribution boundary

The configured PyPI names for Relay, Canon and Mneme identify other projects.
The configured registry entries for Plexus, Telos and accountable-surface are
unavailable. Flywheel blocks package installation and package-selected execution
for these six lanes, including external commands from the frozen client.
Their Lanes cards omit Install, and plugin discovery omits package commands.
The Python engine can still use their source checkouts. This restriction also
applies to installed wheels until a distinct distribution or verified runtime
adapter is available. A matching package version alone is not engine identity.

The engine and native client share one version. Installer signing, clean-machine
installation, physical Android acceptance, and provider-specific authentication
remain separate acceptance checks. This update does not establish model
uplift or migrate unsupported provider sessions.
