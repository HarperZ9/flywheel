"""model_dialects.py -- where each provider puts the facts about a call.

This is data, not logic. model_usage reads it, model_reasoning reads it, and
model_observation maps a backend kind onto it. Adding a provider is an edit
here and nowhere else.

Every path below was read out of a primary source on 2026-09-11 and then put
through an adversarial check that tried to overturn each spelling and each
meaning: the OpenAPI-generated openai-python and openai-node types, the
Anthropic messages reference, the Gemini generateContent reference and the
Vertex discovery document, ollama's api/types.go, vLLM's protocol module, the
OpenRouter generated spec, and llama.cpp's server tree. Where a vendor's
rendered doc page and its generated SDK disagreed, the SDK was taken and the
disagreement is noted beside the entry.

Two arithmetic conventions differ across providers, and both are recorded as
data because a layer that sums tokens without them is wrong in a direction it
cannot detect:

- INPUT_INCLUDES_CACHE_READ. OpenAI, Gemini and ollama count cached prompt
  tokens INSIDE the input figure. Anthropic counts them beside it: the vendor
  states total input = input_tokens + cache_creation_input_tokens +
  cache_read_input_tokens. Adding cache reads to input is right for one
  convention and double-counts the other.
- OUTPUT_INCLUDES_REASONING. OpenAI states reasoning_tokens are counted in
  completion_tokens, and Anthropic states thinking_tokens are billed inside
  output_tokens. Gemini is the other way: totalTokenCount is documented as
  prompt + thoughts + candidates, so thoughtsTokenCount sits OUTSIDE
  candidatesTokenCount. ollama documents no thinking-token figure at all, so
  its entry is None, which means unknown and not False.

A meaning maps to a TUPLE OF ALTERNATIVE PATHS, tried in order, first one
present wins. This exists because four vendors ride the OpenAI response schema
with different cache spellings: DeepSeek adds prompt_cache_hit_tokens, vLLM
spells its cache-write key created_cache_tokens, OpenRouter spells the same
thing cache_write_tokens. One spelling per meaning would drop the cache figure
for whichever vendors lost the coin flip, and drop it silently.

Only the leaf name of a count is never enough to identify it. OpenAI's chat
endpoint nests cached_tokens under prompt_tokens_details and OpenAI's Responses
endpoint nests the same leaf under input_tokens_details, so a reader keyed on
the leaf crosses two endpoints of one vendor. Every entry here is a full path
for that reason.
"""
from __future__ import annotations

OPENAI = "openai"
OPENAI_RESPONSES = "openai-responses"
ANTHROPIC = "anthropic"
GEMINI = "gemini"
OLLAMA = "ollama"
DIALECTS = (OPENAI, OPENAI_RESPONSES, ANTHROPIC, GEMINI, OLLAMA)

# Where the usage block sits inside a response. An empty path means the counts
# are on the response itself, which is what ollama does.
BLOCK = {
    OPENAI: ("usage",),
    OPENAI_RESPONSES: ("usage",),
    ANTHROPIC: ("usage",),
    GEMINI: ("usageMetadata",),
    OLLAMA: (),
}

MEANINGS = {
    OPENAI: {
        "input": (("prompt_tokens",),),
        "output": (("completion_tokens",),),
        "total": (("total_tokens",),),
        # cached_tokens is the cache READ count. cache_write_tokens is a
        # different key in the same object and is the write count; the two are
        # easy to swap and the vendor docstrings are the only thing separating
        # them. DeepSeek's prompt_cache_hit_tokens is the same quantity under
        # its own name, kept as a fallback for responses that carry only it.
        "cache_read": (("prompt_tokens_details", "cached_tokens"),
                       ("prompt_cache_hit_tokens",)),
        "cache_write": (("prompt_tokens_details", "cache_write_tokens"),
                        ("prompt_tokens_details", "created_cache_tokens")),
        "reasoning": (("completion_tokens_details", "reasoning_tokens"),),
    },
    # A different endpoint on the same vendor, with its own spellings. No
    # backend in this repo speaks it today; it is mapped because the failure it
    # prevents is silent. Reading a Responses body with the chat map above finds
    # none of its keys and reports every count absent, which is indistinguishable
    # from a provider that sent no usage at all.
    OPENAI_RESPONSES: {
        "input": (("input_tokens",),),
        "output": (("output_tokens",),),
        "total": (("total_tokens",),),
        "cache_read": (("input_tokens_details", "cached_tokens"),),
        "cache_write": (("input_tokens_details", "cache_write_tokens"),),
        "reasoning": (("output_tokens_details", "reasoning_tokens"),),
    },
    ANTHROPIC: {
        "input": (("input_tokens",),),
        "output": (("output_tokens",),),
        "cache_read": (("cache_read_input_tokens",),),
        "cache_write": (("cache_creation_input_tokens",),),
        # The two TTL buckets below sum to cache_write above, so a cost layer
        # meters one level or the other and never both. They are captured
        # separately because they do not price alike: a one-hour cache write
        # costs more per token than a five-minute one, and a total that mixes
        # them cannot be split back apart afterwards.
        "cache_write_5m": (("cache_creation", "ephemeral_5m_input_tokens"),),
        "cache_write_1h": (("cache_creation", "ephemeral_1h_input_tokens"),),
        # Read-only decomposition of output_tokens, not an addition to it.
        "reasoning": (("output_tokens_details", "thinking_tokens"),),
    },
    GEMINI: {
        "input": (("promptTokenCount",),),
        "output": (("candidatesTokenCount",),),
        "total": (("totalTokenCount",),),
        "cache_read": (("cachedContentTokenCount",),),
        # Present on thinking-enabled models, but a vendor forum report has it
        # absent on at least one of them, so absent here is not proof that no
        # thinking happened.
        "reasoning": (("thoughtsTokenCount",),),
        # No cache-write key exists. Gemini creates a cache through a separate
        # API whose token count never appears on a generate response, so a
        # cache_write reading for this dialect would have to be invented.
    },
    OLLAMA: {
        "input": (("prompt_eval_count",),),
        "output": (("eval_count",),),
        # ollama's own CLI computes uncached as max(0, PromptEvalCount-cached),
        # which is the source for this being a subset rather than a sibling.
        "cache_read": (("prompt_eval_cached_count",),),
    },
}

INPUT_INCLUDES_CACHE_READ = {
    OPENAI: True,
    OPENAI_RESPONSES: True,
    ANTHROPIC: False,
    GEMINI: True,
    OLLAMA: True,
}

OUTPUT_INCLUDES_REASONING = {
    OPENAI: True,
    OPENAI_RESPONSES: True,
    ANTHROPIC: True,
    GEMINI: False,
    OLLAMA: None,        # unknown, and unknown is not False
}

# Whether a count missing from a response means only "the provider did not
# report it". False for ollama: every field of its metrics struct is tagged
# omitempty, so a genuine zero is dropped from the JSON and arrives as an
# absent key. On that dialect absent is ambiguous between nothing-happened and
# nothing-was-said, and a reading that claims to tell them apart is claiming
# more than the wire carries.
ABSENT_MEANS_UNREPORTED = {
    OPENAI: True,
    OPENAI_RESPONSES: True,
    ANTHROPIC: True,
    GEMINI: True,
    OLLAMA: False,
}

# The model name the server put on its own answer, in order of preference. Not
# always the name that was asked for: a router, an alias or a gateway can answer
# with something else, and the served name is the one a receipt has to carry.
# ollama fills remote_model when it proxied the call to a cloud host, and in
# that case its own model field names the local alias rather than the model that
# ran, so the remote name is read first. llama-server ignores the requested name
# entirely and answers with its own alias or the GGUF filename, which is why a
# served name differing from the requested one is a fact to record and not a
# fault to raise on.
SERVED = {
    # A routing proxy answers with two names and they routinely disagree.
    # Top-level model is the route the request addressed, which on OpenRouter
    # may be a slug that resolves to any of several providers or an :auto route
    # chosen per call. choices[].message.model is documented as the "Model that
    # generated this assistant message". Reading only the first names the route
    # and claims it was the model, which is the same trap as ollama's
    # remote_model below, except that on a router it is the ordinary case
    # rather than the exception. Absent everywhere else, so the fallback
    # answers for a direct vendor call.
    OPENAI: (("choices", 0, "message", "model"), ("model",)),
    OPENAI_RESPONSES: (("model",),),
    ANTHROPIC: (("model",),),
    GEMINI: (("modelVersion",),),
    OLLAMA: (("remote_model",), ("model",)),
}

# A cost the provider charged for the call, named and pathed, where a provider
# reports one at all. A figure here was MEASURED by the party doing the billing,
# so it outranks the same call priced locally from a token count and a rate
# card, and the two disagreeing is the single most useful cost signal there is:
# it means the local table is stale, the tier is different, or the served model
# was not the requested one.
#
# These are amounts, not counts, so they are read separately from MEANINGS and
# never pass through the whole-count check. They carry the provider's own unit,
# which for OpenRouter is credits, and nothing here converts between units or
# adds a figure from one provider to a figure from another.
#
# The paths sit on the OPENAI dialect because OpenRouter speaks that schema. A
# direct OpenAI or vLLM response simply has no such key and reads absent, which
# is the correct answer rather than a wrong one.
REPORTED_COST = {
    OPENAI: (
        ("cost", ("usage", "cost")),
        ("upstream_inference_cost",
         ("usage", "cost_details", "upstream_inference_cost")),
        ("upstream_inference_prompt_cost",
         ("usage", "cost_details", "upstream_inference_prompt_cost")),
        ("upstream_inference_completions_cost",
         ("usage", "cost_details", "upstream_inference_completions_cost")),
        ("server_tool_cost", ("usage", "cost_details", "server_tool_cost")),
    ),
    OPENAI_RESPONSES: (),
    ANTHROPIC: (),
    GEMINI: (),
    OLLAMA: (),
}

# Whether the provider billed its own key rather than the caller's. Read beside
# the cost because it changes what the cost means: on a bring-your-own-key call
# the upstream charge landed on the caller's own provider account and only the
# routing fee is owed here.
BYOK = {OPENAI: ("usage", "is_byok")}

# Reasoning text is not part of the OpenAI schema. Every key below on the
# OPENAI dialect is a third-party extension to it: DeepSeek and Z.ai emit
# reasoning_content, OpenRouter, ollama's own OpenAI endpoint and vLLM from
# v0.12 emit reasoning, and llama-server emits reasoning_content. vLLM removed
# the reasoning_content mirror somewhere after v0.15, so a reader that kept only
# that spelling goes quietly empty against a current server. Reading both is how
# one adapter serves every OpenAI-compatible server, and the key that answered is
# reported so a reader knows which convention was in play.
#
# The path is anchored at choices[].message deliberately. DeepSeek carries a
# second field of the same name at choices[].logprobs which holds a token array
# rather than text, and a reader keyed on the leaf name would find it.
OPENAI_REASONING_KEYS = ("reasoning_content", "reasoning")

# Backend kind, as endpoints.py and the provider table spell it, to the response
# schema that kind actually speaks. The dialect is a property of the response
# shape, not of the vendor: a local llama-server speaking the OpenAI schema is
# the openai dialect even though no OpenAI service was involved. A kind absent
# here is unmapped, and an unmapped kind yields a record that says so rather
# than one that guesses.
BY_KIND = {
    "openai": OPENAI,
    "openai-compat": OPENAI,
    "deepseek": OPENAI,
    "glm": OPENAI,
    "zai": OPENAI,
    "openrouter": OPENAI,
    "vllm": OPENAI,
    "llamacpp": OPENAI,
    "lmstudio": OPENAI,
    "togetherai": OPENAI,
    "groq": OPENAI,
    "anthropic": ANTHROPIC,
    "gemini": GEMINI,
    "ollama": OLLAMA,
}


def dialect_for(kind) -> "str | None":
    """The response schema a backend kind speaks, or None if unmapped."""
    return BY_KIND.get(kind) if isinstance(kind, str) else None


__all__ = ["ABSENT_MEANS_UNREPORTED", "ANTHROPIC", "BLOCK", "BYOK", "BY_KIND",
           "DIALECTS", "GEMINI", "INPUT_INCLUDES_CACHE_READ", "MEANINGS",
           "OLLAMA", "OPENAI", "OPENAI_REASONING_KEYS", "OPENAI_RESPONSES",
           "OUTPUT_INCLUDES_REASONING", "REPORTED_COST", "SERVED",
           "dialect_for"]
