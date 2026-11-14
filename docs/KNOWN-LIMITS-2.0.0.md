# Known limits in 2.0.0

An independent security review of the 2.0 gateway and coding session ran on
2026-11-14 and ranked 22 findings. The two that blocked the release and the
five marked "fix before release" are fixed, with seven of the smaller ones.
This page lists what was left as it is, with the reason, so that nobody has
to find it again. `docs/GATEWAY-INTERFACES.md` has the gateway's behaviour in
full.

## Left as they are

| Limit | What it means for you | Why it was left |
|---|---|---|
| No per-key request size, rate or connection limit beyond calls in flight | A key holder can send bodies up to 32 MiB and open many connections. Calls in flight are bounded per key; refused requests still cost the gateway a thread and a body read. | A rate limiter is a feature of its own. The in-flight limit bounds what reaches a provider. |
| Key totals are not tamper-evident | `gateway-keys.json` holds limits and totals in a file any process of the same user can rewrite. It cannot be used to mint a key. On POSIX the file is owner-only. | The totals are a running sum for enforcement. The gateway ledger is the record to check them against. |
| The receipt covers the gateway's reading of a reply, not the bytes delivered | On Messages pass-through, thinking blocks, citations and provider tool blocks reach the client and are outside the receipt's hash. The hash covers the reply's text and tool calls. | A second hash over the delivered bytes changes the receipt format, which was frozen for 2.0.0. |
| Coding session: a `TOOL name {json}` line quoted in a native reply's prose runs as a call | It goes through the same permission prompt as any call, and the ledger records it as a call. Tool output that contains the next call's header can move where one result ends and the next begins. | The fix is in the session's tool loop, which other parts are pinned to. It needs its own change and its own tests. |
| The estimate for a call with no reported counts is a word count | Text without spaces (CJK, minified code, base64) is charged far too little. This applies to upstreams that report no usage, which are local and compatible hosts. | The charge is the same named estimate the reply carries as `x_usage_estimate`. Changing one without the other would make the two disagree. |
| Every refusal with a ledger entry appends one | A key that keeps sending refused requests grows the ledger. In-flight and reservation refusals are not recorded, so the common retryable case does not. | Collapsing repeats loses the count of attempts, which is part of the record. |
| A call that fails after the provider answered is not charged, except an unfinished stream | A plain reply the gateway refuses as malformed, or one that claims a client tool result, was billed by the provider and costs the key nothing. | Such replies carry no trustworthy counts to charge from. They are recorded as failed with the reason. |
| A gateway that stops between a provider's reply and the ledger append leaves no entry | The provider billed the call and the ledger does not show it. | A "call started" entry before each call would double the appends. It is the first candidate for 2.1. |
| Keys share one provider account | Provider prompt caches are shared across keys, so `cache_read_input_tokens` can show one key holder that another caller recently sent the same prefix. | This is how one credential behind a gateway works. Use separate provider accounts where that matters. |
| Other pass-through fields are not allow-listed | A key can still set `service_tier`, `container`, `thinking` and other Messages fields on a request to an Anthropic upstream. `max_tokens` can be capped per key. | The three that open per-use fees or new tool surfaces are allow-listed. The rest change token cost, which the budget counts. |
| `/v1/messages/count_tokens` does not apply the pass-through allow-lists | A key can send any `anthropic-beta` value on a token-count request. | The request runs no tool and the provider does not bill it. |
| Token-count requests and in-flight slots | `count_tokens` takes no in-flight slot and no reservation. | It is not billed. |
| Removed hook wrappers exit 1 quietly | After an upgrade, a client configured with an old hook path captures nothing until `flywheel traces doctor` is run, if the client hides hook errors. | Printing the doctor's line at `flywheel up` is a small change that was not made in time. |
| The SDK compatibility tests may be skipped on CI | The tests that drive the gateway with the `anthropic` and `openai` Python SDKs skip when the packages are not installed. Whether CI installs them was not confirmed. | It needs a CI job that installs both and fails on a skip. |
| Upstream redirects are refused, not followed | An upstream base URL that answers with a redirect now fails with that status. Set the base URL to the final address. | Following a redirect would re-send the provider key to the new host. |

## Budget limits in one list

A budget on a virtual key is an operating limit for a tool you run. It is not
a hard cap on what a provider can bill.

- One call that runs alone can cross a limit by its own cost: its input plus
  up to its output limit. The next call is refused.
- Calls that run together reserve their output limit and a quarter of their
  request bytes. They can cross a limit by the input each one used beyond
  that reservation, over at most the key's in-flight limit (4 by default).
- A call with no reported counts is charged a word estimate, which runs low.
- An unfinished stream is charged an estimate of what was received, not the
  provider's final count.
- A call that fails after the provider answered, other than an unfinished
  stream, is not charged.
- Fees that are not tokens (web search per search, code execution per
  container hour) are not counted. A key cannot cause them unless its
  allow-list names the tool.
- Totals, in-flight counts and reservations live in one Flywheel home and one
  gateway process. Two machines do not share them.
- There is no requests-per-minute limit.
