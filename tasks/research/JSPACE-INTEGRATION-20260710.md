# J-space / Jacobian-lens integration -- what to adopt, what to skip (2026-07-10)

Continues [workspace_signature_design_20260706.md](workspace_signature_design_20260706.md)
and [workspace_perception_20260706.md](workspace_perception_20260706.md). Intake of
five external sources the operator supplied; ranked by falsifiable mechanism, not
by how exciting the branding is.

## Sources (confidence: high they say what is summarized; fetched 2026-07-10)

- **transformer-circuits.pub/2026/workspace** (Anthropic). The "J-space": a small
  set of residual-stream directions (~6-10% of activation variance) that are
  verbalizable, causally load-bearing, flexibly generalizable, and selective. The
  **Jacobian lens** identifies them: `lens(h_l) = softmax(W_U * norm(J_l * h_l))`,
  where `J_l = E[dh_final / dh_l]` averaged over ~1000 contexts. It transports a
  mid-layer activation into the output basis, revealing what that layer is
  "disposed to verbalize". Beats the logit lens because it corrects for
  representational drift across layers. Quantified: swapping a J-lens vector
  ("Soccer"->"Rugby") changes the model's report 88% of the time; the J-space
  component is 6-7% of a concept vector's variance yet drives 59% of swap success.
- **lesswrong "Models are blind outside the J-space, NLAs aren't"**. The
  load-bearing finding for us: the model self-reports its J-space ~80% of the
  time and the non-J residual ~0%, though the non-J part carries ~70% of the
  vector's energy and still moves outputs (+13.7 to +21.1 nats logit uplift from
  injected "subconscious" concepts the model denies holding). NLAs (trained
  decoders, ~80% reconstruction) read both regions.
- **jspace-viz + lens registries** (Apache-2.0). `Festyve/jspace-lenses` (the
  operator's link, verified 2026-07-10) ships one fitted lens: **deepseek-coder-1.3b**
  (a code model). A second, more comprehensive registry, **`solarkyle/jspace-lenses`**
  (github.com/solarkyle/jspace), ships ~9 lenses INCLUDING code-capable ones
  (`gpt-oss-20b`, `Qwen3.6-27B`, `Mistral-Small-24B`) plus a 4-bit Qwen port
  (`WeZZard/jlens-qwen36`) and **router weights for hallucination detection**
  (directly a demote signal). Both are format-interchangeable with the reference
  impl `anthropics/jacobian-lens` (Apache-2.0). Key deployment fact: "one lens per
  model, ANY quantization" -- a lens fit once transfers across quant formats, so
  it works on our served NF4/Q4 model without refitting. A layer x position
  workspace heatmap runs on HF causal LMs. Fitting cost ~40 WikiText prompts.
  (Correction to an earlier claim by the research sweep: Festyve DOES exist -- it
  is the operator's deepseek-coder-1.3b lens -- and solarkyle is a SEPARATE,
  broader registry; both are real.)
- **flexy.design**. An AI design studio for architects (text-to-Rhino geometry).
  NOISE for the engine; at most minor UI inspiration (persistent multi-panel
  canvas) for the projected-world surface.

## The connection that matters (ACTIONABLE, conceptual, no code required)

**J-space blindness is independent, activation-level evidence for our central
measured result.** The selector ablation found self-authored selection earns
**+0pts** (self-test 3/61, McNemar p=1.0) while an external oracle earns **+20pts**
(15/61, p=0.0015). Until now that was a measurement without a mechanism. The
J-space finding supplies the mechanism: **self-verification is confined to the
model's narrow verbalizable workspace; the model is blind to the ~90% of its own
activation energy that an external check can still read.** "The moat is external
verification, not the weights" is now predicted by an independent line of work,
not only observed in our harness. Falsifier that would break BOTH: a model that
could self-verify as well as an external oracle. Our data (self earns zero) and
theirs (self-report ~0% on the non-J residual) agree it cannot.

This also retires an honest gap in the perception thread. The stronger
flexible-generalization test returned **COPY-ONLY** (1/4 functions) and marker 5
(precedence) was "weakest without interpretability access". The J-lens IS that
access, and its "workspace loading" metric (cosine of a concept to its lens
vector) is exactly what we called "workspace-loaded". So the tool that was
missing now exists.

## The integration principle that keeps C2 intact

C2 (HARNESS.md): **no learned model sits in the accept path.** A J-lens is a
model-derived transport; an NLA is an explicitly trained decoder. Using either to
ACCEPT a candidate would put a learned/derived judge on the accept path and break
C2. Therefore:

> **Workspace signals are DEMOTE-ONLY advisories. They may lower confidence or
> escalate; they may never grant acceptance.** The accept authority stays the
> external oracle, or the deterministic consensus gates. This is the same shape as
> the correlation gate we just added: it can only make the engine MORE cautious.

By construction this is C2-clean, because a signal that can only add caution never
becomes an authority. It also directly attacks the residual seam we named while
hardening the selector: consensus cannot tell agree-and-correct from
agree-and-wrong. A workspace read gives a signal behavioral consensus structurally
lacks (does the model's workspace show the right intermediate forming, or show
"evaluation / fake / uncertainty" markers), used ONLY to demote a shaky
CONSENSUS_PASS to LOW_CONFIDENCE so the adaptive loop raises N or escalates.

## Ranked adoption

**ACTIONABLE**

1. **Ground the thesis (done in this pass).** Record the J-space <-> external-vs-self
   connection in PROJECT.md provenance. Zero code, real strengthening.
2. **Workspace-lens advisory interface, demote-only (built this pass as a spec +
   C2-clean interface, NOT a fitted lens).** `harness/workspace_lens.py`: the
   contract for a caution signal, the demote-only integration point in `select()`,
   and a graceful no-op when no lens/activations are available. Honest boundary:
   the SIGNAL SOURCE needs white-box activation access (serve.py / HF, not the
   ollama path) and a fitted lens; neither is wired yet. What is real today is the
   safe SHAPE of the integration.
3. **Diagnostic + demo: visualize the local model's workspace on our tasks.** Run a
   real CODE-model lens over the 61 headroom tasks, focusing on tasks that stay 0/N
   at every temperature (`evaluate_rpn`, `cron_field_expand`): does the workspace
   heatmap differ on solved vs never-solved tasks? Use `solarkyle/jspace-lenses`
   `gpt-oss-20b` (a real code lens), not the 1.3b toy. **Pre-falsifier (run first):**
   if the layer x position heatmap looks identical on solved vs failed tasks, the
   read carries no usable signal on our distribution and the advisory is removed.
4. **Fit a Qwen2.5-Coder-14B J-lens for the served model (gated on #3).** De-risked
   now: solarkyle already ships a `Qwen3.6-27B` lens and a 4-bit Qwen port, and a
   lens transfers across quantizations ("one lens per model, any quant"), so it
   works on our NF4/Q4 serve path without refit. **Deployment falsifier:** the
   workspace-demoted subset of CONSENSUS_PASS answers must have a strictly LOWER
   oracle-pass rate than the non-demoted subset; if equal, the advisory is noise
   and is removed. (Note: the demote hook is already built AND tested --
   `tests/test_selector.py` covers demote / null no-op / never-touch-oracle-PASS /
   never-promote / lens-fault tolerance; no "missing test" step remains.)

**INSPIRATION (note, do not build yet)**

- **Counterfactual reflection training** (shape what the model WOULD say to shape
  what it does). Relevant to the CPT lane, a real research direction, not a quick
  win. Our CPT already showed a load-bearing negative on general benchmarks; this
  would be a different objective, tracked separately.
- flexy.design's persistent multi-panel canvas, for the projected-world UI only.

**NOISE / out of scope**

- The consciousness framing. We already hold a strict functional-access, no-
  phenomenal-claim boundary; J-space is functional-access work and fits inside it.
  Do not import consciousness claims on the back of it.
- Putting an NLA (a trained decoder) anywhere near the accept path. It is a fine
  DIAGNOSTIC lens; it is a C2 violation as an authority.

## Build order with falsifiers

1. workspace_lens.py demote-only interface + no-op fallback + `select()` hook.
   *Falsifier:* a caution signal must be able to demote a CONSENSUS_PASS to
   LOW_CONFIDENCE and must NEVER promote a LOW_CONFIDENCE to an accept; with no
   lens present the engine behaves byte-identically to today. (Built + tested.)
2. jspace-viz on deepseek-coder-1.3b over ~10 headroom-style tasks.
   *Falsifier:* on a task the model fails at every temperature, the workspace
   heatmap should show a missing or wrong intermediate; if the workspace looks
   identical on solved vs failed tasks, the read carries no usable signal and we
   stop here.
3. Only if #2 shows signal: fit a Qwen-14B lens and wire the advisory into the
   real serve.py activation path. *Falsifier:* the workspace-demoted subset of
   CONSENSUS_PASS answers should have a LOWER oracle-pass rate than the
   non-demoted subset; if not, the signal is noise and the advisory is removed.

The discipline throughout: the workspace read is a DIAGNOSTIC and an ADVISORY, and
it earns a place in the engine only by a measured reduction in confident-wrong
consensus, verified against the same oracle we already trust. No claim rides on a
lens we have not fitted.
