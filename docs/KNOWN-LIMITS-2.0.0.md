# Known limits in 2.0.0

An independent security review of the 2.0 gateway and coding session ran on
2026-11-14 and ranked 22 findings. One more was added the same day (Lean
child processes inherited the whole environment), which makes 23. Fixed: the
two that blocked the release, the five marked "fix before release", the added
one, and nine of the smaller ones, one of those in part. A second review, by
a reviewer who had not written the fixes, then found nine further items:
three marked "should fix before release", two "fix after" and four notes. All
nine are fixed. This page lists what was left as it is, with the reason and
what to do about it, so that nobody has to find it again.
`docs/GATEWAY-INTERFACES.md` has the gateway's behaviour in full.

## Left as they are

| Limit | What it means for you | Why it was left |
|---|---|---|
| No per-key request size, rate or connection limit beyond calls in flight | A key holder can send bodies up to 32 MiB and open many connections. Calls in flight are bounded per key; refused requests still cost the gateway a thread and a body read. | A rate limiter is a feature of its own. The in-flight limit bounds what reaches a provider. |
| Key totals and key settings are not tamper-evident | `gateway-keys.json` holds a key's limits, totals, allow-lists, output cap, in-flight limit and suspension flag in a file any process of the same user can rewrite. Such a process can widen a list or clear a suspension. It cannot mint a key. On POSIX the file is owner-only. | The totals are a running sum for enforcement. The gateway ledger is the record to check them against. |
| The receipt covers the gateway's reading of a reply, not the bytes delivered | On Messages pass-through, thinking blocks, citations and provider tool blocks reach the client and are outside the receipt's hash. The hash covers the reply's text and tool calls. | A second hash over the delivered bytes changes the receipt format, which was frozen for 2.0.0. |
| Coding session: tool output that contains the next call's result header moves where one result ends and the next begins | When one native reply holds several calls, the outputs can be divided at the wrong place on the way back to the provider, and the next result's ok or FAIL mark can flip on that wire. The text still arrives whole and in order. The ledger and what you are asked do not change. | The fix is in the session's tool loop, which other parts are pinned to. It needs its own change and its own tests. |
| The estimate for a call with no reported counts is a word count | Text without spaces (CJK, minified code, base64) is charged far too little. This applies to upstreams that report no usage, which are local and compatible hosts. | The charge is the same named estimate the reply carries as `x_usage_estimate`. Changing one without the other would make the two disagree. |
| Every refusal with a ledger entry appends one | A key that keeps sending refused requests grows the ledger. In-flight and reservation refusals are not recorded, so the common retryable case does not. | Collapsing repeats loses the count of attempts, which is part of the record. |
| A call that fails after the provider answered is not charged, except an unfinished stream | A plain reply the gateway refuses as malformed, or one that claims a client tool result, was billed by the provider and costs the key nothing. | Such replies carry no trustworthy counts to charge from. They are recorded as failed with the reason. |
| A gateway that stops between a provider's reply and the ledger append leaves no entry | The provider billed the call and the ledger does not show it. | A "call started" entry before each call would double the appends. It is the first candidate for 2.1. |
| Keys share one provider account | Provider prompt caches are shared across keys, so `cache_read_input_tokens` can show one key holder that another caller recently sent the same prefix. | This is how one credential behind a gateway works. Use separate provider accounts where that matters. |
| Other pass-through fields are not allow-listed | A key can still set `service_tier`, `container`, `thinking` and other Messages fields on a request to an Anthropic upstream. `max_tokens` can be capped per key. A field that changes the price of a token (`service_tier` and similar) is not seen by a spend limit, which multiplies the token counts by the prices you gave the key. | The three that open per-use fees or new tool surfaces are allow-listed. Set a token limit, which no price change affects, on a key whose holder you do not want choosing a service tier. |
| `/v1/messages/count_tokens` is outside the key controls and the ledger | A key can send any `anthropic-beta` value on a token-count request. The request takes no in-flight slot and no reservation, is not charged to the key, and leaves no ledger entry, although the provider is contacted. | The request runs no tool and the provider does not bill it. |
| Removed hook wrappers exit 1 quietly | After an upgrade, a client configured with an old hook path captures nothing until `flywheel traces doctor` is run, if the client hides hook errors. | Printing the doctor's line at `flywheel up` is a small change that was not made in time. |
| Upstream redirects are refused, not followed | An upstream base URL that answers with a redirect now fails with that status. Set the base URL to the final address. | Following a redirect would re-send the provider key to the new host. |

## The gateway ledger and slow or abandoned requests

These were written down by the second review. Each is how the gateway works
in 2.0.0, with what to do where it matters to you.

| Limit | What it means for you | What to do |
|---|---|---|
| One gateway process per Flywheel home | Only one process can append to a home's ledger. A second gateway on the same home, or a gateway whose `gateway-ledger` folder cannot be written, answers every model call with 503 and sends nothing to a provider. It says so in one line at start. | Run one gateway per home. Give a second gateway its own `FLYWHEEL_HOME`. If the start line says `LEDGER UNAVAILABLE`, stop the other gateway or fix the folder; the gateway tries again on each call. |
| The 503 covers the routes that write to the ledger | `/v1/messages`, `/v1/messages/count_tokens`, `/v1/responses`, `/v1/chat/completions` with a provider endpoint, and `/api/route` are refused when the ledger is unavailable. The local model on the chat path (`flywheel`, `serve`, `local`) and the gateway's own agent, companion and evaluation routes never wrote to this ledger and are not refused. | The gateway ledger is the record of provider calls made through those five routes only. |
| A stream's text leaves before its ledger entry exists | The entry holds the hash of the whole reply, so it is written when the stream ends, before the last event. A gateway that is killed in the middle of a stream has delivered text and has no entry for it. | Treat a stream without its last event (`message_stop`, `response.completed`) as unrecorded. A plain reply is always recorded before it is sent. |
| On a pass-through stream, a refused reply has already reached the client | An Anthropic upstream's events are relayed as they arrive. A reply the gateway refuses at its end (a claimed client tool result, a malformed reply) was already delivered. The refusal means an error event, no receipt, and a failed entry. | Do not act on a streamed reply that ended with an error event and has no `x_receipt`. |
| `FLYWHEEL_GATEWAY_LEDGER_SYNC=0` trades durability for speed | With it, an entry is not committed to the disk before the gateway goes on. A crash of the gateway loses nothing. A power loss can lose the newest entries. | Leave it unset unless the 1 to 3 ms per call matters more than the last entries before a power loss. |
| The ledger shows a shortened file, not every rewrite | A removed entry, a changed byte and a missing segment make `flywheel gateway-ledger verify` fail. A process of the same user that rewrites a segment and the head record together, or removes the whole folder, is not detected by the files alone. | Run `flywheel anchor` to have an outside party witness a head, and keep the ledger folder out of reach of processes you do not trust. |
| The read timeout is per read, not per request | A client that sends nothing for 30 seconds (`FLYWHEEL_GATEWAY_READ_TIMEOUT`) is closed. A client that keeps sending a few bytes holds its connection and a gateway thread for longer. It gains no spend that way: a key's limits are read again once the body is whole. | Put the gateway behind a proxy with its own request deadline if it is reachable by clients you do not run. |
| The read timeout covers reads only | It applies to the request line, headers and body of every gateway route. Writes have no timeout: a client that stops reading a stream keeps its connection and its in-flight slot until it closes or the provider's stream ends. | The in-flight limit bounds how many such calls a key can hold. Lower `--in-flight` for a key whose holder you trust less. |
| A stream abandoned before its first event is charged for the prompt only | The gateway closes the upstream connection when the client has gone. A provider may still bill output it produced before it noticed. The entry says `"abandoned": true` and `"estimated": true`. | Compare the ledger with the provider's own usage page if a key's holder drops connections often; the in-flight limit bounds how many such calls run at once. |
| The Lean allow-list keeps profile and toolchain paths | A Lean child process gets the variables it needs to start: home and temp folders, locale, `PATH` and the toolchain names. Candidate proof code can print those into `kernel_output`. No provider key, proxy setting or `FLYWHEEL_` variable is passed. | Do not put a secret in a folder name or in `PATH` on a machine that checks proofs from a source you do not trust. |

## Budget limits in one list

A budget on a virtual key is an operating limit for a tool you run. It is not
a hard cap on what a provider can bill.

- One call that runs alone can cross a limit by its own cost: its input plus
  up to its output limit. The next call is refused.
- Calls that run together reserve their output limit and a quarter of their
  request bytes. They can cross a limit by the input each one used beyond
  that reservation, over at most the key's in-flight limit (4 by default).
  A request is checked against the totals as they are once its body has
  arrived, so a client gains nothing by sending headers early and bodies late.
- A call with no reported counts is charged a word estimate, which runs low.
- An unfinished stream is charged the provider's output count when one had
  arrived, and otherwise a word estimate of what was received (text,
  tool-call arguments and thinking), not the provider's final count.
- A call that fails after the provider answered, other than an unfinished
  stream, is not charged.
- Fees that are not tokens (web search per search, code execution per
  container hour) are not counted. A key cannot cause them unless its
  allow-list names the tool.
- Totals, in-flight counts and reservations live in one Flywheel home and one
  gateway process. Two machines do not share them.
- There is no requests-per-minute limit.
