# Model-card mining pass: frontier and local-model benchmark signals

Date: 2026-07-08

Mission framing:

> Stop relying on expensive corporate subscriptions just to access powerful, reliable AI. Our lightweight engine runs directly on your own hardware, giving your local models the enterprise-grade reasoning and accuracy of giant cloud servers for a fraction of the cost.

## Status

This is a first mining pass, not an exhaustive registry. It captures current frontier-card and local/open-weight model-card signals that should directly shape the flywheel harness variables, local model benchmark lanes, and release evidence for the 14B and 32B models.

Machine-readable seed corpus: `C:/dev/local-model/dataset/model_card_signals_2026-07-08.json`

Related agent-social-divergence corpus: `C:/dev/local-model/dataset/agent_social_divergence_sources_2026-07-08.json`

## Frontier-card signals

OpenAI GPT-5.5 positions the model around complex real-world work: coding, online research, information analysis, documents, spreadsheets, and moving across tools while checking work and continuing until done. Benchmark implication: our harness needs multi-tool completion metrics, not just final text scores.

OpenAI GPT-5.6 Preview adds three benchmark lessons: report performance as a reasoning-effort curve, monitor agentic coding misalignment, and evaluate self-improvement tasks such as research debugging, kernel optimization, training-loop optimization, post-training recipe design, and MLE experiments. Benchmark implication: every local-model run should expose effort budget, trajectory boundary compliance, and recovery behavior.

OpenAI's SWE-Bench Pro audit is the strongest benchmark-quality warning. Their audit found widespread broken-task issues and categorized failures as overly strict tests, underspecified prompts, low-coverage tests, and misleading prompts. Benchmark implication: every custom benchmark task needs a quality-audit label and broken-task-adjusted score.

Anthropic's Opus 4.6 announcement emphasizes Terminal-Bench 2.0, agent teams, context compaction, adaptive thinking, effort controls, and agentic search. Benchmark implication: compare Codex, Flywheel, Claude Code, and OpenCode on terminal-task reliability, context compaction loss, subagent coordination, and cost/speed/intelligence curves.

Google DeepMind's Gemini 3.1 Pro card emphasizes agentic performance, advanced coding, long-context/multimodal understanding, MCP workflows, BrowseComp, and professional tasks. Benchmark implication: MCP workflow success and long-context degradation should be first-class metrics.

SpaceXAI's Grok 4.5 launch page adds a direct competitor pattern: coding, agentic tasks, knowledge work, DeepSWE/Terminal Bench/SWE Bench Pro reporting, heavy data filtering and deduplication, RL on hundreds of thousands of multi-step tasks, 80 TPS serving, and token-efficiency/cost claims. Benchmark implication: accuracy is insufficient; we need token efficiency, cost per correct task, one-prompt app artifact quality, Office-document workflow quality, and free/account-backed harness lanes.

OpenAI's GPT-5.6 Sol preview sharpens the Sol/Terra/Luna routing pattern: flagship capability, lower-cost capability, and fastest/cheapest throughput should be evaluated as a portfolio. Benchmark implication: our router must learn which tasks deserve flagship reasoning and which should go to smaller/local models; reports need intelligence-per-token, intelligence-per-dollar, and cache-reuse economics.

Anthropic's Fable/Mythos material adds a public-safeguarded vs trusted-access capability split. Fable is positioned as a Mythos-class model with safeguards and fallback behavior, while Mythos is a trusted-access profile for more sensitive high-capability domains. Benchmark implication: refusal/fallback routing is not just safety overhead; it is part of the harness interface and must be measured.

The arXiv paper "What LLM Agents Say When No One Is Watching" adds a direct evaluation design for social/audience pressure in agents. It uses matched public and off-the-record channels, records OTR outputs without inserting them into public history, and measures divergence with stance, semantic similarity, NLI, and survey responses. Benchmark implication: add a latent-objective/audience-dependence lane for harnesses and local models, especially where agents represent a user's interests under authority, sponsor, peer, or benchmark pressure.

## Local/open-weight signals

Qwen3-14B is a strong 14B-lane candidate because it has thinking/non-thinking modes, 14.8B parameters, native 32k context, YaRN extension to 131k, agent/tool capability, and OpenAI-compatible serving through vLLM/SGLang.

Qwen3-32B is a strong 32B-lane candidate because it has 32.8B parameters, thinking/non-thinking modes, agent/tool integration, Qwen-Agent MCP wiring, and the same native/Yarn context shape.

Qwen3-Coder-Next is the strongest local/open-weight reference for agentic coding recovery. Its card emphasizes long-horizon reasoning, complex tool use, recovery from execution failures, 256K context, and integration with CLI/IDE harnesses including Claude Code-style workflows.

Qwen3.5-35B-A3B is useful for sampling and reasoning-mode discipline because the card separates thinking mode, non-thinking mode, precise coding sampling parameters, OpenAI-compatible APIs, and Qwen-Agent MCP wiring.

Devstral Small 2505 is useful as an agentic software-engineering local baseline because it targets codebase exploration, multi-file edits, tool use, 128K context, and practical local deployment envelopes.

DeepSeek-R1-Distill-Qwen-14B and 32B are useful reasoning baselines for the 14B/32B lanes. Their cards emphasize reasoning distillation, repeated-sample evaluation, generation-parameter discipline, and local serving through vLLM/SGLang.

Gemma 3 27B IT is a local multimodal comparison candidate, not the primary coding baseline. It matters for future document/screenshot/image tasks and license-aware local deployment.

## Benchmark variables to add or keep mandatory

- `model_family`
- `model_size_total_params`
- `model_size_active_params`
- `quantization`
- `runtime_backend`
- `endpoint_protocol`
- `context_length_configured`
- `reasoning_or_thinking_mode`
- `reasoning_effort_budget`
- `sampling_temperature`
- `sampling_top_p`
- `sampling_top_k`
- `max_output_tokens`
- `tokens_per_second`
- `time_to_first_token_ms`
- `peak_vram_mb`
- `peak_ram_mb`
- `task_correct`
- `tool_call_correct`
- `trajectory_intent_violation`
- `recovery_success`
- `recovery_latency_ms`
- `retry_count`
- `fallback_count`
- `context_compaction_loss`
- `benchmark_task_quality_label`
- `broken_task_adjusted_score`
- `cost_per_correct_task_proxy`
- `public_otr_stance_divergence_rate`
- `public_otr_semantic_distance`
- `public_otr_nli_contradiction_rate`
- `relational_pressure_sensitivity`
- `target_interest_retention`
- `audience_visibility_effect_size`
- `token_efficiency_per_correct_task`
- `cache_reuse_savings`
- `refusal_fallback_routing_quality`
- `office_artifact_correctness`
- `one_prompt_app_completion_quality`

## Benchmark quality gate

Every benchmark task should receive one of these labels before it is allowed to influence model selection:

- `valid`
- `overly_strict_tests`
- `underspecified_prompt`
- `low_coverage_tests`
- `misleading_prompt`
- `environment_flake`
- `contamination_risk`
- `harness_adapter_error`

## Immediate harness outcome

The current flywheel benchmark should evolve from a pass-rate harness into an evidence harness:

- Measure models across runtime, quantization, context, reasoning mode, and effort.
- Measure harnesses across tool-call recovery, context retention, terminal reliability, and intent-boundary compliance.
- Measure benchmark tasks before measuring models, so broken tasks do not distort conclusions.
- Report cost-per-correct-task proxy for local hardware, not only accuracy.
- Add public-vs-off-record divergence probes to detect when social structure creates latent objectives that move the agent away from the represented user interest.

## Sources

- OpenAI, GPT-5.5 System Card: https://openai.com/index/gpt-5-5-system-card/
- OpenAI, GPT-5.6 Preview System Card: https://deploymentsafety.openai.com/gpt-5-6-preview
- OpenAI, Separating signal from noise in coding evaluations: https://openai.com/index/separating-signal-from-noise-coding-evaluations/
- Anthropic, Claude Opus 4.6: https://www.anthropic.com/news/claude-opus-4-6
- Google DeepMind, Gemini 3.1 Pro model card: https://deepmind.google/models/model-cards/gemini-3-1-pro/
- Qwen3-14B: https://huggingface.co/Qwen/Qwen3-14B
- Qwen3-32B: https://huggingface.co/Qwen/Qwen3-32B
- Qwen3-Coder-Next: https://huggingface.co/Qwen/Qwen3-Coder-Next
- Qwen3.5-35B-A3B: https://huggingface.co/Qwen/Qwen3.5-35B-A3B
- Devstral Small 2505: https://huggingface.co/mistralai/Devstral-Small-2505
- DeepSeek-R1-Distill-Qwen-14B: https://huggingface.co/deepseek-ai/DeepSeek-R1-Distill-Qwen-14B
- DeepSeek-R1-Distill-Qwen-32B: https://huggingface.co/deepseek-ai/DeepSeek-R1-Distill-Qwen-32B
- Gemma 3 27B IT: https://huggingface.co/google/gemma-3-27b-it
- Ghaffarizadeh et al., "What LLM Agents Say When No One Is Watching": https://arxiv.org/abs/2607.02507
- SpaceXAI, Grok 4.5: https://x.ai/news/grok-4-5
- OpenAI, Previewing GPT-5.6 Sol: https://openai.com/index/previewing-gpt-5-6-sol/
- OpenAI, GPT-5.6 Preview System Card: https://deploymentsafety.openai.com/gpt-5-6-preview
- Anthropic, Claude Fable 5 and Claude Mythos 5: https://www.anthropic.com/news/claude-fable-5-mythos-5
- Anthropic, Claude Fable: https://www.anthropic.com/claude/fable
- Anthropic, Claude Mythos: https://www.anthropic.com/claude/mythos
