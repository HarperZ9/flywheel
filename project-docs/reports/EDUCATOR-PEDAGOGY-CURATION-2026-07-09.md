# Educator pedagogy curation (2026-07-09)

Source research for [PEDAGOGY.md](../PEDAGOGY.md). Distilled from two web
research passes on the four educators the operator named plus their peers. Every
strong claim is cited or marked inferred in the notes below; nothing here quotes
video content, since no videos were watched or transcribed.

## Scope boundary honored

For Alisa Esage (offensive security research), only teaching method, learning
philosophy, and mindset were curated. No exploit code, payloads, or attack steps
were collected or reproduced. The framing throughout is defensive and
verification-oriented.

## The four, in one line each

- Numberphile (Brady Haran and guest mathematicians): rigor made accessible by
  hook-first structure, the expert as the star, and concrete low-fidelity
  visuals. Peers: 3Blue1Brown (visuals before formalism, rediscovery),
  Mathologer (aesthetic proof over a hidden review layer), Veritasium
  (misconception-first, backed by Derek Muller's PhD research), Stand-up Maths
  (comedy as a delivery vehicle, not a substitute for correctness).
- Anton Petrov (What Da Math): wonder-forward daily distillation of primary
  literature, a fixed warm opener, calm and non-alarmist. Peers: Kurzgesagt
  (disclosed research pipeline and per-video source sheets), PBS Space Time
  (depth without a ceiling), Sabine Hossenfelder (stated no-hype ethos, with the
  honest caveat that credentialed critics find her skepticism has tipped toward
  alarmism).
- Alisa Esage (Zero Day Engineering): self-taught first-principles mastery,
  fuzzing framed from first principles, independent vendor-adversarial practice,
  training built on real targets not toy puzzles. Peers: LiveOverflow
  (concept-first, progressive-difficulty curriculum), Gynvael Coldwind
  (learn-by-practice, write-then-reverse-your-own-binary, multi-mode analysis),
  the coverage-guided fuzzing literature (AFL: retain and evolve only inputs
  that reach new states).
- Zachary Huang (ZacharyLLM, Microsoft Research): minimalist agent frameworks
  (PocketFlow, 100 lines), the graph abstraction for agents, "LLM agents are
  just loops with branches," and realistic-task benchmarks over synthetic ones.
  Peers: the llama.cpp quantize documentation (the quant ladder, imatrix
  calibration, perplexity and KL divergence), Unsloth's dynamic-GGUF methodology
  (KLD over perplexity, calibration-contamination warning, per-layer quant), and
  the QLoRA fine-tuning education community.

## Confidence and provenance notes

- High confidence, directly fetched written sources: Numberphile format,
  3Blue1Brown's four explainer criteria and rediscovery principle, Derek
  Muller's misconception-first research result, Matt Parker's teaching
  background and awards, Kurzgesagt's fact-checking pipeline, Gynvael Coldwind's
  learn-by-practice method, the AFL coverage-guided approach, Zachary Huang's
  identity and PocketFlow, the llama.cpp quant docs, and Unsloth's calibration
  and KLD guidance.
- Moderate or inferred: Anton Petrov's explicit "we do not know yet" framing was
  inferred from his consistently calm tone rather than a sourced quote; some
  Mathologer and Petrov points came from search snippets of pages that could not
  be directly fetched; the specific mathematical content of Esage's fuzzing talk
  is inferred from its title and venue, not watched; the ZacharyLLM channel's
  stated training-data goal came from secondary summaries. These are flagged so
  the synthesis does not overclaim.

## What was produced from this

The distillation became two lists in PEDAGOGY.md: a Voice we want (12 principles
for public docs) and a Discipline we want (10 principles for verification), plus
a Where this lands section tying each to real components. The through-line: lead
with wonder, earn trust by trying to break things, and show your work.
