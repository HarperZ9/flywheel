# Flywheel: a companion for every model

Date: 2026-07-09

## The short version

Flywheel is not trying to replace the models you already reach for. It is a
companion layer that helps every model, local or frontier, do its best work
and prove it. Think of it as a looking glass held up to the frontier: the
capability is the model's, and flywheel is the lens that keeps the picture
honest and lets you carry it home.

There are two moving parts, and they are meant to be small.

- A local model, `Flywheel-Local-Coder-14B`, that runs entirely on your own
  machine as a single file just under 9 GB. A 32B sibling is training now.
- A verification harness, the flywheel itself, that runs beside any model:
  the model proposes, an oracle checks, and every accepted answer carries a
  receipt anyone can re-run.

The model is the replaceable half. The harness is the durable half. That is
by design.

## Why a companion, and not a competitor

The frontier is moving quickly and it is worth being honest about where the
capability lives. As of today, the strongest coding and reasoning belongs to
hosted models: OpenAI's GPT-5.6 tier (Sol, Terra, Luna) reached general
availability this morning after a government pre-release review, and
Anthropic's Mythos-class models (Fable 5 in the open, Mythos 5 behind trusted
access) set the pace on the hardest evaluations. We are not going to pretend a
9 GB file on a desktop out-reasons those systems. It does not, and saying so
plainly is part of the point.

What none of those surfaces give you today is a portable, checkable record of
what an agent actually did, and a way to spend the expensive model only on the
part of a task that genuinely needs it. Availability is also not fully in your
hands: Fable 5 was taken offline within days of release by an export directive,
Mythos 5 is gated to approved organizations, and Sol cleared a review window
before launch. A companion that runs on weights you hold is available on a
schedule you control, and it can sit underneath any of these models to make
each one go further.

So the frame is not flywheel versus the frontier. It is flywheel plus the
frontier: a lens that makes the model in front of you, whichever one it is,
more efficient and more accountable to you.

## The seam we are closing

For a while there has been a small tear in the fabric of how we work with
these systems. A model does something useful, and then the evidence of what it
did lives only inside a session, or inside a vendor's server, and you either
trust it or you do not. The record is not yours to keep or to check.

Flywheel's answer is quiet and concrete. Every accepted answer carries a
receipt: the inputs, the check that passed, and hashes that let anyone re-run
the verification offline, without trusting our machine or anyone's. You do not
have to take this on faith. The strongest audit available is the one you run
yourself, and flywheel is built so that you can.

That is the whole of the accountability story here, and it is meant to be a
doorway, not the house. Walk through it once and then get on with the work.

## What we are building toward

The direction is steady and it points at your own hardware.

- Better models in smaller packages. The 14B runs on an ordinary machine
  today. The work ahead is quantization and distillation that keep more of the
  capability in less space, so more of this reaches more people on the hardware
  they already own.
- The companion sitting between a harness and a frontier model, caching the
  sub-results it has already verified, and routing only the genuinely hard
  slice of a task to the expensive tier while handling the rest locally. This
  is a design direction, not a shipped feature yet, and this document will not
  claim otherwise until the receipts exist.
- Speaking the protocols everyone already uses, so flywheel drops in without
  ceremony: the OpenAI-compatible endpoint, the Model Context Protocol at both
  its current and its incoming stateless versions, the Ollama API, and the
  hook and subagent surfaces that modern harnesses expose.
- Models you can hold, and eventually train yourself, on your own corpus, with
  a provenance chain that proves what went in.

## The tone we want to keep

It would be easy to sell this on fear: your data, your dependence, your risk.
We would rather sell it on wonder. There is something genuinely moving about a
capable model living in a single file on your own disk, working on an airplane,
working when the network is down, answering to you and to a check you can read.
The receipts are there so that trust is never required, which is a kind of
freedom, not a kind of suspicion.

The invitation is simple. Bring whatever model you like. Flywheel will stand
beside it, help it do its best work, and hand you a record you can keep.

## Honest status, today

- `Flywheel-Local-Coder-14B` is a real trained artifact with a verified
  provenance chain, a passing live endpoint gate, and first benchmark evidence.
  It is staged for release and waiting on the operator's approval to upload.
- No capability uplift over the base model is claimed. The easy benchmark set
  saturates; the discriminating measurement is a larger hard-set run, and until
  that lands with confidence intervals, the honest measurable claims are
  reproducible receipts, pass parity, and local cost.
- The 32B model is training now. It will enter the same release path, with the
  same evidence bar, and it will not be published until the evidence is
  something an outside observer can check.

This document will keep pace with the receipts, and not get ahead of them.
