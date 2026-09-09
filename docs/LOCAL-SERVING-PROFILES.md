# Reproducible Ollama context settings

An endpoint being reachable does not establish that a model fits in GPU memory or
can complete a request. Large context allocations can force CPU offload. Pin the
model variant and requested context before comparing local runs.

Generate profiles for an existing local model directory:

```sh
python scripts/run_model_endpoint_profiles.py --models 14B,32B --base-root /path/to/models --ollama-num-ctx 8192 --out /path/to/results/profiles.json
python scripts/run_model_endpoint_gate.py --profile-artifact /path/to/results/profiles.json --backends ollama --timeout-seconds 120 --max-tokens 32 --out /path/to/results/gate.json --strict-exit
```

Endpoint-gate rows are readiness evidence. New rows record
`metric_source_kind: endpoint_readiness`, `readiness_score`, and
`quality_score_semantics: endpoint_readiness_not_task_quality`. The legacy
`quality_score` field remains in the row for compatibility with older receipts,
but comparison and coverage reports treat endpoint-gate artifacts as health,
generation, latency, and failure evidence; they do not create task-quality
winners or uplift claims.

The profile command defaults to 8192 context tokens and exact Qwen2.5-Coder
`14b-instruct-q4_K_M` / `32b-instruct-q4_K_M` base selectors. Override them with
`--ollama-model-14b` and `--ollama-model-32b` to match installed variants. This
does not download models or change the trained-release selectors. Profile
generation is metadata only; inspect every gate row, including failed rows.

Model and backend filters can select several profiles. To admit a single probe,
copy its exact `profile_id` from the generated artifact and add
`--profile-id PROFILE_ID --max-generation-calls 1` to the gate command.
An absent or duplicate ID fails before endpoint I/O. The call cap counts the
maximum possible generations across the entire selected plan, including profiles
that may later fail health checks. An over-budget plan fails before any health or
generation request; it never silently truncates coverage. The JSON
`generation_plan` records the selected IDs, cap and admission decision. Omitting
these options preserves multi-profile probing with no call cap. The cap covers
this gate invocation only; subsequent experiments need their own budget.

For the standalone local agent:

```sh
python -m harness.local_agent_cli --backend ollama --model qwen2.5-coder:32b-instruct-q4_K_M --num-ctx 8192 --json "Explain the difference between a list and a tuple."
```

`OllamaBackend(num_ctx=8192)` sends the same setting in streaming and ordinary
requests. The local agent's returned `generation_config` records the options
sent, and its request hash binds those options. Successful generation gate rows
record them too; retain the hash-bound profile alongside failure rows. The
cross-harness local adapter consumes the configuration from the selected,
hash-bound profile. Unknown configuration keys and invalid context values fail
before a request. Accepted values are integers from 1 to 1048576; that input
range does not assert that a particular model supports or can fit every value.

Existing profiles that omit `generation_config`, and standalone CLI calls that
omit `--num-ctx`, retain server-controlled context. They do not claim an observed
server context. Check Ollama's `/api/ps` for the loaded context and memory, and
retain the runtime version, model digest, hardware and cache state separately.
The request receipt proves the requested configuration, not server compliance.

8192 is a bounded evaluation default, not an automatic fit calculation. It can
reduce usable task context relative to larger settings. Measure long-context
accuracy separately; a successful short probe proves neither task quality nor
speed superiority. Compare cold and warm runs separately with fixed tasks and
budgets, retaining timeouts in the denominator.

These controls cover the standalone local agent and local evaluation adapters.
The general gateway and desktop provider settings need their own configuration
path; this change does not add a native model-settings interface.
