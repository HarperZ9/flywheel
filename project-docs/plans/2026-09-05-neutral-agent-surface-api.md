# A neutral action surface for agents: assessment and first build

Status: exploration. Nothing here is built. Written 2026-09-05.

## The ask

A vendor-neutral API that lets any LLM, harness, or agent operate surfaces that
resist automation. YouTube, Discord, and Reddit were named. The stated payoff is
token efficiency and shorter project timelines. It would be native to Flywheel
and reachable over the web through bulletin, so another workstation or another
vendor's agent can call it.

## What already exists

Researched 2026-09-05 against live sources. Three categories are occupied.

**Delegated-auth tool catalogs.** Composio runs an MCP gateway over a catalog of
roughly 500 apps with managed OAuth. Arcade.dev positions itself as an MCP
runtime where the agent acts as the user through OAuth delegation rather than a
bot token, with tool-level authorization and an evaluation harness for
tool-calling behavior. Pipedream Connect, Nango, and Zapier MCP sit in the same
band. Every surface with an official API is already served here, and all three
named surfaces publish one.

**Browser infrastructure.** Browserbase persists cookies and local storage so an
agent stays logged in across runs. Steel carries a session over CDP with
long-lived browsers and a live viewer. Browser Use sells stealth explicitly:
residential proxies, CAPTCHA solving, anti-detection. Vercel ships an
agent-browser CLI. A local engine is the documented setup when the task needs
the operator's own cookies.

**Agent identity at the edge.** Web Bot Auth is an IETF individual draft led by
Cloudflare. An agent signs each request with an Ed25519 key using HTTP Message
Signatures (RFC 9421) and a Signature-Agent header that points at a JWKS
directory. Cloudflare activated verification at its edge in March 2026, and AWS
WAF, Akamai, HUMAN, and Vercel verify the signatures. No working-group document
was adopted as of August 2026, so the standard is shipping ahead of its
ratification.

The access problem is therefore solved twice: once by borrowing the user's OAuth
grant, once by hiding. The identity problem is being solved by the parties who
run the gate.

## What this workspace already owns

Read from code, not from README claims.

`accountable-surface` carries the contract the proposed API needs.
`src/accountable_surface/effector.py` defines a frozen `Plan` (action kind,
target, content hash, reversibility, prior existence, and a content-addressed
digest), a `Verdict`, and a `RefusedActuation` raised when there is no gate
allow, when a receipt fails to match the plan, or when a target falls outside
the construction bound. An effector is inert until authorized for that exact
plan, and it re-perceives afterward so the surface can verify the effect. Four
effectors are implemented: filesystem, command, browser over a Playwright
driver, and web over an HTTP driver. `grant.py` holds the operator gate and
`journal_chain.py` holds the tamper-evident record.

`bulletin` already registers ed25519 identities on an open web surface. It is
merged and waiting on a deploy.

`gather` reaches gated APIs, paywalls, JS-walled pages, and scanned PDFs.
`telos` holds workstation control. `plexus` discovers what a tool emits and
consumes, then wires producers to consumers. `crucible` measures a thesis
against a substrate and refines the weakest axis, which makes it the natural
evaluator for whether a surface pack earns its place. `forum` supplies routing
and a replayable causal ledger.

Four of the five pieces exist. What is absent is a per-surface verb pack and a
public endpoint that a remote agent can call.

## Verdict on the wedge

The idea as stated is occupied, and entering it directly would put a
single-maintainer project against funded incumbents on their own ground.

A narrower claim is open. Nobody in either access category hands back a receipt.
Composio returns a result. Browserbase returns a result. Neither returns
evidence a third party can check offline: what the agent proposed, what the
operator authorized, what changed, and a hash chain binding those together. The
enforcement layer is moving toward agents that prove who they are, which makes
stealth the shrinking side of the market and delegated auth the growing side.
Delegated auth stops at authentication and says nothing about what the agent
then did.

So the wedge is an **accountable action surface**: the same verbs, where every
call carries a signed plan, an operator grant, and a re-perceived verification,
so the caller can prove afterward what its agent did on the operator's account.
That is defensible here because the substrate is already written.

Honest limit, and it is a real one. No evidence was found that anyone pays for
this today. Receipt framing was judged dead once in this workspace already, for
signed evaluation scores, on the grounds that the space was crowded and
astroturfed. The claim here is narrower, covering accountability for actions
taken on the operator's own accounts rather than model scores, and it remains
unvalidated demand. Treat it as exploration until a user asks for it.

## The boundary, and how the adapter resolves it

No detection evasion. That excludes residential proxy rotation, CAPTCHA
solving, fingerprint spoofing, and anything built to make an automated request
resemble a human one. It also excludes Discord user tokens, which that platform
treats as self-bots and bans on sight.

The first draft of this plan proposed driving the operator's own logged-in
session where a site published no usable API, and flagged the account risk that
creates. The operator's answer was better: build an **API adapter**. Agents call
one neutral surface, and that surface calls each platform's sanctioned API. The
account risk disappears because no session is ever driven, and the value moves
from access to normalization.

What the adapter is actually worth, given that the underlying APIs are public:

- One verb vocabulary across surfaces, so an agent writes `search` once instead
  of learning three request shapes and three pagination schemes.
- Quota arithmetic the caller would otherwise get wrong. YouTube Data API v3
  meters in units against a default 10,000 per day per Google Cloud project,
  where a read costs 1 unit and a search costs 100, so roughly 100 searches
  exhaust a day. Reddit allows 100 queries per minute per OAuth client on the
  free non-commercial tier. Discord rate-limits per route and globally, with a
  sliding window. An adapter that knows each budget can refuse, queue, or
  degrade before the caller is throttled.
- Compact results. The token claim rests here: a normalized record instead of a
  rendered page.
- A receipt per call, which is the part nobody else ships.

Honest limits on the adapter, worth knowing before any code is written:

- Reddit closed self-service OAuth registration in late 2025 under its
  Responsible Builder Policy. New clients go through manual approval reported at
  two to four weeks, with silent rejection possible. Commercial use is priced by
  hand and reported near $0.24 per 1,000 calls with a large monthly minimum.
  Confidence: moderate; these figures come from secondary trackers rather than a
  published Reddit rate card, because Reddit no longer publishes one.
- An adapter cannot exceed what the official API exposes. Where a platform's API
  omits a capability, the honest answer to the calling agent is that the verb is
  unavailable on that surface.
- Every adapter inherits the platform's terms. Redistribution of fetched content
  is governed by them, not by this surface.

## Smallest build that settles it

One surface pack, end to end, on the substrate already here. Reddit is the right
first pick: documented API, a published rate limit, and a read path that needs
no write authority.

1. Define a `SurfacePack` protocol with `verbs()`, `plan(verb, args) -> Plan`,
   and `perceive(target) -> Observation`, reusing the existing gate and journal
   rather than introducing a second authorization path.
2. Implement `reddit` with `read_thread` and `search`. API path only, no writes.
3. Measure against a browser-driving agent on the same task with crucible:
   tokens spent, wall clock, and correctness of the result. Token efficiency is
   the claim that motivated this, so it is the number that decides.
4. If the margin holds, add one write verb behind a grant and expose the pack
   through bulletin so a remote agent can reach it.

Kill criterion: if the pack fails to beat a browser-driving agent on tokens for
the same task by a wide margin, the premise is wrong and the work stops at step
three.

## Sources

- Arcade.dev and Composio positioning: scalekit.com/blog/arcade-alternatives,
  scalekit.com/blog/composio-alternatives, nango.dev/blog/best-mcp-servers-for-agent-api-integrations/
- Browser infrastructure: browserbase.com/browse-cli, llms.steel.dev/articles/,
  browser-use.com/stealth-browsers, github.com/vercel-labs/agent-browser
- Web Bot Auth: datatracker.ietf.org/doc/draft-meunier-webbotauth-httpsig-protocol/,
  datatracker.ietf.org/doc/html/draft-meunier-web-bot-auth-architecture,
  blog.cloudflare.com/verified-bots-with-cryptography/
