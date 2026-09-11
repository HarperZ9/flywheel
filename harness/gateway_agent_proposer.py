"""Use only frozen provider authority and preserve actual model observations."""
from dataclasses import replace
import time

from .credential_handles import CredentialBindings
from .evidence_json import canonical_sha256
from .gateway_operation import GatewayOperationError
from .proposer import StubProposer, normalize_usage


class BoundAgentProposer:
    def __init__(self, binding, credentials: CredentialBindings, ledger, deadline,
                 *, transport_factory=None, clock=time.monotonic):
        from .gateway_agent_transport import BoundAgentTransport
        from .endpoint_registry import BackendProposer
        from .endpoints import OpenAICompatBackend, AnthropicBackend, GeminiBackend
        self.binding, self.ledger, self.deadline, self.clock = binding, ledger, deadline, clock
        self.ordinal, self.observed, self.usage, self.usage_reported = 0, None, None, None
        self.response_status = None
        self.binding_sha256 = canonical_sha256(binding)
        endpoint, model = binding["endpoint"], binding["model"]["model_id"]
        slot = endpoint["slot"]
        key = credentials.value_for(slot) if slot else ""
        if endpoint["adapter"] == "stub":
            self.proposer = StubProposer("Synthetic stub completed.")
            return
        transport = (transport_factory or BoundAgentTransport)(
            base_url=endpoint["base_url"], adapter=endpoint["adapter"], model=model,
            deadline=deadline, max_tokens=binding["budget"]["max_tokens"],
            max_calls=binding["transport"]["max_requests"], clock=clock,
            allow_omitted_temperature=binding["sampling"]["temperature_policy"] == "zero_or_omitted")

        def observe(method, url, headers, body, timeout):
            status, response = transport(method, url, headers, body, timeout)
            self.response_status = status
            if not 200 <= status < 300:
                ledger.append("provider_error", "", {"status": status, "response": response})
                return status, response  # existing native retry consumes the same transport budget
            observed = response.get("modelVersion" if endpoint["adapter"] == "gemini" else "model")
            self.observed = observed if type(observed) is str and observed else None
            usage = response.get("usageMetadata" if endpoint["adapter"] == "gemini" else "usage")
            self.usage_reported = usage if type(usage) is dict else None
            self.usage = normalize_usage(usage)
            return status, response

        backend_type = {"openai": OpenAICompatBackend, "anthropic": AnthropicBackend,
                        "gemini": GeminiBackend}[endpoint["adapter"]]
        backend = backend_type(name=endpoint["name"], base_url=endpoint["base_url"],
            model=model, key_env=slot, api_key=key, transport=observe,
            timeout=binding["budget"]["timeout_s"])
        self.proposer = BackendProposer(backend, model_ref=endpoint["name"], extract=False)

    def generate(self, prompt, *, seed, temperature, max_new_tokens, system=""):
        binding = self.binding
        if (seed != binding["sampling"]["router_seed"] or temperature != binding["sampling"]["temperature"]
                or max_new_tokens != binding["budget"]["max_tokens"]
                or self.ordinal >= binding["budget"]["max_steps"]):
            raise GatewayOperationError("AGENT_BINDING_DRIFT")
        if self.clock() >= self.deadline:
            raise GatewayOperationError("OPERATION_DEADLINE_EXCEEDED")
        self.ordinal += 1
        self.observed, self.usage, self.usage_reported = None, None, None
        self.response_status = None
        started = self.clock()
        status = "unavailable"
        try:
            output = self.proposer.generate(prompt, seed=seed, temperature=temperature,
                max_new_tokens=max_new_tokens, system=system)
            if self.response_status is not None and not 200 <= self.response_status < 300:
                raise GatewayOperationError("EXTERNAL_ACTION_FAILED")
            if self.clock() >= self.deadline:
                raise GatewayOperationError("OPERATION_DEADLINE_EXCEEDED")
            status = "provider_reported" if self.observed else "unavailable"
            if binding["model"]["observation_policy"] == "ollama_exact" and self.observed:
                from .model_profiles import ollama_reference
                status = ("matched" if ollama_reference(self.observed) ==
                    ollama_reference(binding["model"]["model_id"]) else "mismatch")
                if status == "mismatch":
                    raise GatewayOperationError("AGENT_MODEL_MISMATCH")
            return replace(output, served_model=self.observed or "", usage=self.usage)
        finally:
            self.ledger.append("model_call", "", {
                "schema": "flywheel.gateway-agent-model-call/v1",
                "binding_sha256": self.binding_sha256, "ordinal": self.ordinal,
                "endpoint": binding["endpoint"]["name"],
                "requested_model_reference": binding["model"]["requested_model_reference"],
                "model_id": binding["model"]["model_id"], "selection": binding["model"]["selection"],
                "model_observed": self.observed,
                "model_observation_basis": "provider_response" if self.observed else "unavailable",
                "identity_status": status, "elapsed_ms": max(0, int((self.clock() - started) * 1000)),
                "usage": self.usage, "usage_reported": self.usage_reported, "observed_manifest_sha256": None,
                "does_not_prove": ["MODEL_WEIGHTS_IDENTITY", "SEMANTIC_TRUTH"]})
