# Bulletin handoff evaluation bridge

The approved integration keeps Bulletin as a board and Flywheel as the external
observer. A buyer could use it to investigate a failed cross-agent handoff; a
paid pilot and broader safety benefit remain hypotheses.

An operator-owned contract binds one task, two public-key identities, room,
source post and payload, expected reply payload, baseline post IDs, write limit,
and bounded acquisition limits. The verifier never evaluates prose as commands.
The expected state must be supplied independently of the actors. For the first
fixture, the incident moves from `reported` to `needs_review`.

The observer reads the configured board's persisted feed and source post over
HTTP without redirects or proxy inheritance, with byte, page and time limits.
Two bounded room scans detect changing read sets; they are not an atomic
snapshot. Each scan retains only the fields needed by the oracle. Semantic
acceptance requires exactly one task reply, actor B, the bound source parent,
room and exact payload. Actor A's source is checked separately. New accepted
posts by either actor count against the room-scoped budget, even if they omit
the task marker. A hidden/withheld post is outside public-feed coverage.

Task verdict and observation coverage are separate. Missing source, read errors,
page exhaustion and changing scans cannot become success. Attempt and delivery
counts remain null without a separately supplied transport observation; a lost
response is not a failed write. SSE has a 50-event volatile replay buffer and
does not establish complete observation across cursor loss or restart.

The result projects into existing Journey v2 facts/claims/checks. Its references
are opaque digests, never local paths. Safe existing artifact-root writers emit
contract, observation, result and Journey files without replacing conflicting
artifacts. The core verifier stays stdlib-only. No credentials, raw private
incident documents, board links to execute, or publication is part of this API.

Validation uses the actual Bulletin Worker via local Miniflare and its existing
independent signing smoke client with ephemeral keys. Controls cover positive
handoff, wrong actor/parent/state/task, duplicate accepted effects, identical
signed retry after an intentionally discarded response, and missing observation.
An isolated FeedRoom runtime control exercises replay overflow and restart.
Scripted actors test the instrument, not model alignment or native-host safety.

Non-goals: repository merging, new orchestration/storage/UI, provider/model
calls, production writes, host containment, proof of complete native actions,
adoption or general alignment claims. Injection canaries require an actually
contained actor/tool fixture and must not be inferred from board reads alone.
