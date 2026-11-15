# Known limits in 2.0.0

An independent security review of the 2.0 gateway and coding session ran on
2026-11-14 and ranked 22 findings. One more was added the same day (Lean
child processes inherited the whole environment), which makes 23. Fixed: the
two that blocked the release, the five marked "fix before release", the added
one, and nine of the smaller ones, one of those in part. A second review, by
a reviewer who had not written the fixes, then found nine further items:
three marked "should fix before release", two "fix after" and four notes. All
nine are fixed. A third review, by another reviewer who had written none of
the fixes, read those fixes and found eleven items: one that blocked the
release (text inside a native tool call's arguments could become a different
call), three marked "document or fix before the tag", two "fix after" and
five notes. Ten are fixed, several with a limit that the tables below state,
and one was a gap in this page that is now closed (`/v1/embeddings` is named
among the routes outside the ledger). The reviewer's own probe scripts were
run again against the fixed code. A fourth reviewer then read those fixes and
found twelve items: one that blocked the release (a request whose text could
not be hashed was served on a stream with no ledger entry and no charge),
three marked "document or fix before the tag", four "fix after" and four
notes, and eight sentences that claimed more than the tests showed. Eight
items were fixed, one in part, and three were stated on this page.

A fifth round then built what the fourth had stated. A call is now in the
ledger before it is made (a started entry, committed to the disk before the
request leaves), so a gateway that is killed leaves an unsettled call that
`flywheel gateway-ledger verify` names; calls in flight when a ledger write
fails get their end entry when the ledger resumes; the chat routes and
`/v1/embeddings` record through the same object as the model interfaces; a
late body is answered 408 on every route; and one rule decides when a key is
suspended. Five rows left this page for that reason. No independent review
of the fifth round has been done.

This page lists what is left as it is, with the reason and what to do about
it, so that nobody has to find it again. The last column of each table says
what would close the row: an issue with a design note, or the reason
software cannot. `docs/GATEWAY-INTERFACES.md` has the gateway's behaviour in
full.

## Left as they are

| Limit | What it means for you | Why it was left | What would close it |
|---|---|---|---|
| No request rate or connection limit, and no per-key size limit, beyond calls in flight | Any client that can reach the gateway's port, with or without a credential, can open many connections, and each holds a gateway thread until its request is read or a deadline passes. A key holder can send bodies up to 32 MiB. Calls in flight are bounded per key; refused requests still cost the gateway a thread and a body read. | A rate limiter and a connection cap are features of their own. The in-flight limit bounds what reaches a provider. Keep the port on loopback or behind a proxy that limits connections. | Issue #489 |
| Key totals and key settings are not tamper-evident | `gateway-keys.json` holds a key's limits, totals, allow-lists, output cap, in-flight limit and suspension flag in a file any process of the same user can rewrite. Such a process can widen a list or clear a suspension. It cannot mint a key. On POSIX the file is owner-only. | The totals are a running sum for enforcement. The gateway ledger is the record to check them against. | Issue #490 |
| The receipt covers the gateway's reading of a reply, not the bytes delivered | On Messages pass-through, thinking blocks, citations and provider tool blocks reach the client and are outside the receipt's hash. The hash covers the reply's text and tool calls. | A second hash over the delivered bytes changes the receipt format, which was frozen for 2.0.0. | Issue #491 |
| Coding session: tool output that contains the next call's result header moves where one result ends and the next begins | When one native reply holds several calls, the outputs can be divided at the wrong place on the way back to the provider, and the next result's ok or FAIL mark can flip on that wire. The text still arrives whole and in order. The ledger and what you are asked do not change. | The fix is in the session's tool loop, which other parts are pinned to. It needs its own change and its own tests. | Issue #492 |
| The estimate for a served call with no reported counts is a word count | Text without spaces (CJK, minified code, base64) is charged far too little. This applies to a reply that was served whole by an upstream that reports no usage, which are local and compatible hosts. An unfinished stream is different: on every upstream, hosted OpenAI included, its input is charged at least a quarter of the request's bytes (tool definitions, images and documents included) and what was received at least a quarter of its characters. | The charge is the same named estimate the reply carries as `x_usage_estimate`. Changing one without the other would make the two disagree. | Issue #493 |
| Every refusal with a ledger entry appends one | A key that keeps sending refused requests grows the ledger. In-flight and reservation refusals are not recorded, so the common retryable case does not. | Collapsing repeats loses the count of attempts, which is part of the record. | Issue #494 |
| A call that fails after the provider answered is not charged, except an unfinished stream | A plain reply the gateway refuses as malformed, or one that claims a client tool result, was billed by the provider and costs the key nothing. | Such replies carry no trustworthy counts to charge from. They are recorded as failed with the reason. | Issue #495 |
| An unsettled call is settled by hand | A gateway that is killed between a provider's reply and the end entry leaves the call's started entry. `verify` names it, and its reservation counts against its key until `flywheel gateway-ledger settle CALL`, where you give what the provider billed. Flywheel does not read that figure from the provider, and it cannot tell a call that was billed from one that never left: the started entry is written before the request does. | The gateway's side of a killed call ends at the started entry. What the provider did with the request is in the provider's records only. | Issue #496 |
| Keys share one provider account | Provider prompt caches are shared across keys, so `cache_read_input_tokens` can show one key holder that another caller recently sent the same prefix. | This is how one credential behind a gateway works. Use separate provider accounts where that matters. | Issue #497 |
| Other pass-through fields are not allow-listed | A key can still set `service_tier`, `container`, `thinking` and other Messages fields on a request to an Anthropic upstream. `max_tokens` can be capped per key. A field that changes the price of a token (`service_tier` and similar) is not seen by a spend limit, which multiplies the token counts by the prices you gave the key. | The three that open per-use fees or new tool surfaces are allow-listed. Set a token limit, which no price change affects, on a key whose holder you do not want choosing a service tier. | Issue #498 |
| `/v1/messages/count_tokens` is outside the key controls and the ledger | A key can send any `anthropic-beta` value on a token-count request. The request takes no in-flight slot and no reservation, is not charged to the key, and leaves no ledger entry, although the provider is contacted. It is the one request the gateway sends with no entry. | It cannot reach anything that bills. It is forwarded only to an Anthropic upstream's `/v1/messages/count_tokens`, which the Claude API documents as free to use with its own rate limit (the token-counting page, "Pricing and rate limits", read 2026-11-14); the gateway answers 404 itself for an OpenAI-format or Gemini upstream; and the code path refuses any other URL. No live call was made to confirm the price. | Issue #499 |
| Removed hook wrappers exit 1 quietly | After an upgrade, a client configured with an old hook path captures nothing until `flywheel traces doctor` is run, if the client hides hook errors. | Printing the doctor's line at `flywheel up` is a small change that was not made in time. | Issue #500 |
| Upstream redirects are refused, not followed | An upstream base URL that answers with a redirect now fails with that status. Set the base URL to the final address. | Following a redirect would re-send the provider key to the new host. | Issue #501 |

## The gateway ledger and slow or abandoned requests

These were written down by the second review. Each is how the gateway works
in 2.0.0, with what to do where it matters to you.

| Limit | What it means for you | What to do | What would close it |
|---|---|---|---|
| One gateway process per Flywheel home | Only one process can append to a home's ledger. A second gateway on the same home, or a gateway whose `gateway-ledger` folder cannot be written, answers every provider call with 503 and sends nothing to a provider. It says so in one line at start. | Run one gateway per home. Give a second gateway its own `FLYWHEEL_HOME`. If the start line says `LEDGER UNAVAILABLE`, stop the other gateway or fix the folder; the gateway tries again on each call. | Issue #502 |
| Calls in flight when a ledger write first fails have already reached the provider | A ledger that opened at start and then stops taking writes (a full disk) is seen at the first append that fails. A call that starts then is refused with 503 before it is sent, because its started entry cannot be written. The calls already in flight had their started entries on disk and their requests out: at most a key's in-flight limit for each key (4 by default), not bounded for the gateway token. Each plain reply is held back and answered 500, each stream's text has left and ends with an error event, and each key is suspended. When the ledger resumes it appends the end entry of each of those calls, marked `late`, after its `ledger_gap` entry. If the failed write left a line cut short, the segment stays as it is and `verify` exits 1 from then on, naming the recorded break. A gateway that is stopped while the disk is still full records nothing more; the calls that were in flight are then unsettled calls. | Watch the gateway log for `GATEWAY LEDGER WRITE FAILED`. Free space. The gateway tries the ledger again when a call comes in, at most once a second. Then read the late entries, and clear each suspended key with `flywheel gateway-key clear NAME`. | Software cannot: a request that has left cannot be recalled. What it can do is done: refuse new calls, and record the calls in flight. |
| The 503 covers the routes that write to the ledger | `/v1/messages`, `/v1/messages/count_tokens`, `/v1/responses`, `/v1/chat/completions` with a provider endpoint, `/api/route` and `/v1/embeddings` are refused when the ledger is unavailable. The local model on the chat path (`flywheel`, `serve`, `local`) never wrote to this ledger and is not refused. The gateway's agent runs keep their own record, a private trace for each run, which gets a started record before each provider request; they are not refused either. | The gateway ledger is the record of provider calls made through those six routes. Over HTTP `/v1/embeddings`, like the chat path, sits behind the per-operation grant flow. | Issue #503 |
| A stream's text leaves before its end entry exists | The end entry holds the hash of the whole reply, so it is written when the stream ends, before the last event. The started entry is on disk before the stream begins. A gateway that is killed in the middle of a stream has delivered text; the ledger then shows the call as unsettled. | Treat a stream without its last event (`message_stop`, `response.completed`) as unrecorded. A plain reply is always recorded before it is sent. | Software cannot write the hash of a reply before the reply exists. A running hash of what was delivered is issue #491. |
| On a pass-through stream, a refused reply has already reached the client | An Anthropic upstream's events are relayed as they arrive. A reply the gateway refuses at its end (a claimed client tool result, a malformed reply) was already delivered. The refusal means an error event, no receipt, and a failed entry. | Do not act on a streamed reply that ended with an error event and has no `x_receipt`. | Software cannot both relay a stream as it arrives and hold it back until its end is checked. |
| `FLYWHEEL_GATEWAY_LEDGER_SYNC=0` trades durability for speed | With it, an entry is not committed to the disk before the gateway goes on, the started entry included. A crash of the gateway loses nothing. A power loss can lose the newest entries, and with them the record that a call was started. | Leave it unset unless the two commits per call (2.3 to 3.7 ms on the measured machine, more on a slow disk) matter more than the last entries before a power loss. | Software cannot have an entry on the disk without waiting for the disk. The setting is your choice between the two. |
| The ledger shows a shortened file, not every rewrite | A removed entry, a changed byte and a missing segment make `flywheel gateway-ledger verify` fail. A process of the same user that rewrites a segment and the head record together, or removes the whole folder, is not detected by the files alone. | Run `flywheel anchor` to have an outside party witness a head, and keep the ledger folder out of reach of processes you do not trust. | Files alone cannot: a process with the same rights can rewrite every file the check reads. A scheduled witness narrows the window: issue #504 |
| Slow clients are bounded by deadlines, not by a connection cap | A client that sends nothing for 30 seconds (`FLYWHEEL_GATEWAY_READ_TIMEOUT`) is closed. A client that keeps sending a few bytes is closed when the request line and headers have taken longer than one timeout (plus at most one more read), and when a request body has taken longer than four; a late body is answered 408 on every route. After a refusal that did not read the body, what the client still sends is discarded for two seconds at most. This holds with or without a credential. Until a deadline passes each such connection holds a gateway thread, and nothing limits how many a client opens. It gains no spend that way: a key's limits are read again once the body is whole. | Put the gateway behind a proxy with its own connection limit if it is reachable by clients you do not run. | Issue #489 |
| The read timeout covers reads only | It applies to the request line, headers and body of every gateway route. Writes have no timeout: a client that stops reading a stream keeps its connection and its in-flight slot until it closes or the provider's stream ends. | The in-flight limit bounds how many such calls a key can hold. Lower `--in-flight` for a key whose holder you trust less. | Issue #505 |
| A stream abandoned before its first event is charged for the prompt only | The gateway closes the upstream connection when the client has gone. A provider may still bill output it produced before it noticed. The entry says `"abandoned": true` and `"estimated": true`. | Compare the ledger with the provider's own usage page if a key's holder drops connections often; the in-flight limit bounds how many such calls run at once. | Issue #496 |
| The Lean allow-list keeps profile and toolchain paths | A Lean child process gets the variables it needs to start: home and temp folders, locale, `PATH` and the toolchain names. Candidate proof code can print those into `kernel_output`. No provider key, proxy setting or `FLYWHEEL_` variable is passed. | Do not put a secret in a folder name or in `PATH` on a machine that checks proofs from a source you do not trust. | The child cannot start without them. Removing their values from the output: issue #506 |

## Written down by the third review

| Limit | What it means for you | What to do | What would close it |
|---|---|---|---|
| The fallback to the text protocol rests on the wording of a provider's error | A model moves from native function calling to the text protocol when its host answers 400, 404 or 422 with a message that says tools or function calling are unsupported. No provider documents that sentence: the Claude API errors page, the OpenAI error-codes guide and the Gemini troubleshooting page were read on 2026-11-14 and none gives one. The phrases Flywheel accepts come from two documented Claude API forms and from error texts quoted in public issue reports for Ollama, Gemini and OpenRouter, which were not checked against a live host. A host that words its refusal another way fails the request. A host that uses one of the phrases for another reason switches the model to the text protocol, where a `TOOL name {json}` line in a reply is a call. The check reads the whole error message, so a host that quotes the request's own text in its error could carry a phrase from a prompt; no such host is known and none was tested. The move holds for every session in the same program, not only the one that met the error. | Each session prints and records one notice when its model moves, also when another session met the error (`native_tools_fallback`). Set `FLYWHEEL_NATIVE_TOOLS=0` for a host that needs the text protocol, and read the notice if you see one you did not expect. | Issue #507 |
| Calls on one key that are in flight together can still cross its limit | A key's row is now read and its slot taken as one step, so a call cannot be admitted on a total that another call finished and changed in between. Two calls that run at the same time are a different case and unchanged: each reserves its output limit and a quarter of its request bytes, and a call whose real input is larger than that crosses the limit by the difference. | Lower `--in-flight` to 1 for a key that must not cross its limit by more than one call's cost. | Issue #508 |
| The static check of the Lean modules reads syntax, not behaviour | The test that scans the Lean modules for a child process started outside the allow-list resolves import aliases and reports `subprocess`, `asyncio.create_subprocess_*`, `os.system`, `os.popen`, `os.startfile`, `os.spawn*`, `os.exec*`, `os.posix_spawn*`, `os.fork`, `pty`, `multiprocessing`, `concurrent.futures`, `getattr` on those modules, a spawn function used as a value, and an `env=` that is not exactly `lean_env(...)`. It does not see a process started through `ctypes` (the Windows sandbox, tested at its call site), `importlib`, `__import__`, `eval` or `exec`, a module reached through a second variable, or a spawn in a module that a Lean module calls. It also misses a function or an assignment named `lean_env` in the module itself, `loop.subprocess_exec` and `loop.subprocess_shell`, a spawn function reached by subscript (`sys.modules[...]`, `subprocess.__dict__[...]`, `vars(...)`, `globals()[...]`), `operator.attrgetter`, and a third-party or standard helper that spawns (`psutil.Popen`, `webbrowser.open`). This list is what two reviews found; it is not complete. | It is a guard against a careless change, not a proof. The tests that record the environment each spawn site hands its child are the stronger check. | A reading of syntax cannot decide what a program does. A check at the spawn itself: issue #509 |
| A resumed ledger can hold more than one `ledger_gap` entry for one outage | When an attempt to resume writes its `ledger_gap` line and the commit to the disk fails again, that line is in the file and is kept at the next attempt, which adds its own. The chain verifies and no sequence number repeats. | Read the `since`, `until` and `appends_refused` fields of each entry; together they cover the outage. | Issue #510 |
| The list of modules that open a network connection is kept by hand | `tests/test_gateway_provider_reach_inventory.py` fails when a module under `harness/` calls `urlopen`, `build_opener`, `create_connection`, `HTTPConnection` or `HTTPSConnection` and is not on its list, so a new provider route has to be written down with the record it leaves. A connection opened another way is not seen, and 24 of the 32 rows say "not examined": those modules are not gateway provider routes and the record they leave was not read in this round. | Treat the list as a prompt for review. It does not prove that every network call is accounted. | A reading of syntax cannot decide what a program does. The watch tests on the transports are the check that runs the code. |

## Budget limits in one list

A budget on a virtual key is an operating limit for a tool you run. It is not
a hard cap on what a provider can bill.

- One call that runs alone can cross a limit by its own cost: its input plus
  up to its output limit. The next call is refused. (issue #508)
- Calls that run together reserve their output limit and a quarter of their
  request bytes. They can cross a limit by the input each one used beyond
  that reservation, over at most the key's in-flight limit (4 by default).
  A request is checked against the totals as they are once its body has
  arrived, so a client gains nothing by sending headers early and bodies late.
- The reservation of an unsettled call (a call whose gateway was killed
  before its end entry) counts against its key until the call is settled
  with `flywheel gateway-ledger settle CALL`.
- A call with no reported counts is charged a word estimate, which runs low.
  (issue #493)
- An unfinished stream is charged the provider's output count when one had
  arrived, and otherwise an estimate of what was received (text, tool-call
  arguments and thinking), not the provider's final count. Its prompt is
  charged the provider's input count when one had arrived. An OpenAI-format
  stream reports usage in its last chunk, so on every such upstream the
  prompt of an unfinished stream is estimated. Each estimate here is the
  larger of the word count and a quarter of the characters, and the input
  estimate is also at least a quarter of the request's bytes, which counts
  tool definitions, images and documents.
- A call that reached the provider and was not fully accounted suspends its
  key until `flywheel gateway-key clear NAME`: its debit failed, its end
  entry could not be written, or its accounting met a fault nobody planned
  for (`accounting_error`). That is one rule, for a reply that was held back
  and for a stream whose text had left. A failed debit is recorded as
  `charged_tokens` 0 with the amount under `uncharged_tokens`.
- A call that fails after the provider answered, other than an unfinished
  stream, is not charged. (issue #495)
- Fees that are not tokens (web search per search, code execution per
  container hour) are not counted. A key cannot cause them unless its
  allow-list names the tool. (issue #496)
- Totals, in-flight counts and reservations live in one Flywheel home and one
  gateway process. Two machines do not share them. (issue #502)
- There is no requests-per-minute limit. (issue #489)
