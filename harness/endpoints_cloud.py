"""endpoints_cloud.py -- models behind Azure OpenAI, Amazon Bedrock and Google Vertex AI.

Standard library only. Each backend has the same shape as the others in
harness/endpoints.py (name, model, health(), chat()) and turns on only when its
settings are present:

  azure    AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_API_KEY, AZURE_OPENAI_DEPLOYMENT
           (AZURE_OPENAI_API_VERSION, default 2024-10-21)
  bedrock  AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_REGION, BEDROCK_MODEL
           (AWS_SESSION_TOKEN when the credentials are temporary)
  vertex   VERTEX_PROJECT, VERTEX_LOCATION, VERTEX_MODEL, and an access token from
           VERTEX_ACCESS_TOKEN or, when that is unset, `gcloud auth print-access-token`

Bedrock requests are signed with AWS Signature Version 4, written here from the
published algorithm; the signature is checked in tests against AWS's own example.
Keys are read at call time (environment, then the OS credential store) and sent
only to their provider.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import hmac
import json
import os
import subprocess
import urllib.parse
from dataclasses import dataclass, field

from .endpoints_http import _guard, _http, _k, _response_error
from .token_usage import from_openai


def _get(name: str) -> str:
    return _k(name) if name.endswith(("_KEY", "_TOKEN")) else os.environ.get(name, "")


@dataclass
class AzureOpenAIBackend:
    name: str = "azure"
    model: str = ""
    transport: "callable" = _http
    timeout: float = 120.0

    def __post_init__(self):
        self.model = self.model or os.environ.get("AZURE_OPENAI_DEPLOYMENT", "")

    def health(self) -> bool:
        return bool(_get("AZURE_OPENAI_ENDPOINT") and _get("AZURE_OPENAI_API_KEY") and self.model)

    def chat(self, messages, *, system, max_tokens, temperature, seed) -> dict:
        base = _get("AZURE_OPENAI_ENDPOINT").rstrip("/")
        version = os.environ.get("AZURE_OPENAI_API_VERSION", "2024-10-21")
        url = (f"{base}/openai/deployments/{urllib.parse.quote(self.model, safe='')}"
               f"/chat/completions?api-version={urllib.parse.quote(version)}")
        msgs = ([{"role": "system", "content": system}] if system else []) + list(messages)
        body = {"messages": msgs, "max_tokens": max_tokens, "temperature": temperature}
        status, obj = _guard(self.transport, "POST", url,
                             {"Content-Type": "application/json",
                              "api-key": _get("AZURE_OPENAI_API_KEY")},
                             json.dumps(body).encode(), self.timeout, self.name)
        try:
            text = obj["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError):
            raise _response_error(self.name, status, obj)
        out = {"text": text, "model_ref": f"azure:{self.model}", "seed": seed}
        usage = from_openai(obj)
        return {**out, "token_usage": usage} if usage else out


# -- AWS Signature Version 4 ----------------------------------------------------

def _hmac(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def sigv4_headers(method: str, url: str, body: bytes, *, region: str, service: str,
                  access_key: str, secret_key: str, session_token: str = "",
                  now: "_dt.datetime | None" = None, extra: "dict | None" = None) -> dict:
    """Headers that sign the request (Authorization, X-Amz-Date, ...)."""
    now = now or _dt.datetime.now(_dt.timezone.utc)
    amz_date, day = now.strftime("%Y%m%dT%H%M%SZ"), now.strftime("%Y%m%d")
    parts = urllib.parse.urlsplit(url)
    headers = {"host": parts.netloc, "x-amz-date": amz_date, **{k.lower(): v for k, v in (extra or {}).items()}}
    if session_token:
        headers["x-amz-security-token"] = session_token
    signed = ";".join(sorted(headers))
    canonical_headers = "".join(f"{k}:{' '.join(str(headers[k]).split())}\n" for k in sorted(headers))
    path = urllib.parse.quote(parts.path or "/", safe="/-_.~")
    query = "&".join(sorted(f"{urllib.parse.quote(k, safe='-_.~')}={urllib.parse.quote(v, safe='-_.~')}"
                            for k, v in urllib.parse.parse_qsl(parts.query, keep_blank_values=True)))
    payload_hash = hashlib.sha256(body).hexdigest()
    canonical = "\n".join([method, path, query, canonical_headers, signed, payload_hash])
    scope = f"{day}/{region}/{service}/aws4_request"
    to_sign = "\n".join(["AWS4-HMAC-SHA256", amz_date, scope,
                         hashlib.sha256(canonical.encode("utf-8")).hexdigest()])
    key = _hmac(_hmac(_hmac(_hmac(("AWS4" + secret_key).encode("utf-8"), day), region),
                      service), "aws4_request")
    signature = hmac.new(key, to_sign.encode("utf-8"), hashlib.sha256).hexdigest()
    out = {k: v for k, v in headers.items() if k != "host"}
    out["authorization"] = (f"AWS4-HMAC-SHA256 Credential={access_key}/{scope}, "
                            f"SignedHeaders={signed}, Signature={signature}")
    return out


@dataclass
class BedrockBackend:
    name: str = "bedrock"
    model: str = ""
    transport: "callable" = _http
    timeout: float = 120.0

    def __post_init__(self):
        self.model = self.model or os.environ.get("BEDROCK_MODEL", "")

    def health(self) -> bool:
        return bool(_get("AWS_ACCESS_KEY_ID") and _get("AWS_SECRET_ACCESS_KEY")
                    and os.environ.get("AWS_REGION") and self.model)

    def chat(self, messages, *, system, max_tokens, temperature, seed) -> dict:
        region = os.environ["AWS_REGION"]
        url = (f"https://bedrock-runtime.{region}.amazonaws.com/model/"
               f"{urllib.parse.quote(self.model, safe='')}/converse")
        body = {"messages": [{"role": m["role"], "content": [{"text": m["content"]}]}
                             for m in messages],
                "inferenceConfig": {"maxTokens": max_tokens, "temperature": temperature}}
        if system:
            body["system"] = [{"text": system}]
        raw = json.dumps(body).encode()
        headers = sigv4_headers("POST", url, raw, region=region, service="bedrock",
                                access_key=_get("AWS_ACCESS_KEY_ID"),
                                secret_key=_get("AWS_SECRET_ACCESS_KEY"),
                                session_token=_get("AWS_SESSION_TOKEN"),
                                extra={"content-type": "application/json"})
        status, obj = _guard(self.transport, "POST", url, headers, raw, self.timeout, self.name)
        try:
            text = "".join(c.get("text", "") for c in obj["output"]["message"]["content"])
        except (KeyError, TypeError):
            raise _response_error(self.name, status, obj)
        out = {"text": text, "model_ref": f"bedrock:{self.model}", "seed": seed}
        u = obj.get("usage") or {}
        if type(u.get("inputTokens")) is int and type(u.get("outputTokens")) is int:
            out["token_usage"] = {"input_tokens": u["inputTokens"], "output_tokens": u["outputTokens"]}
        return out


def _gcloud_token() -> str:
    from . import safe_program
    try:
        argv, env = safe_program.launch(["gcloud", "auth", "print-access-token"])
        p = subprocess.run(argv, env=env, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError, safe_program.ProgramUnavailable):
        return ""
    return p.stdout.strip() if p.returncode == 0 else ""


@dataclass
class VertexBackend:
    name: str = "vertex"
    model: str = ""
    transport: "callable" = _http
    timeout: float = 120.0
    token_source: "callable" = field(default=_gcloud_token)

    def __post_init__(self):
        self.model = self.model or os.environ.get("VERTEX_MODEL", "")

    def health(self) -> bool:
        return bool(os.environ.get("VERTEX_PROJECT") and os.environ.get("VERTEX_LOCATION")
                    and self.model)

    def chat(self, messages, *, system, max_tokens, temperature, seed) -> dict:
        token = _get("VERTEX_ACCESS_TOKEN") or self.token_source()
        if not token:
            raise _response_error(self.name, 401, {"error": "no Vertex access token: set "
                                                   "VERTEX_ACCESS_TOKEN or sign in with gcloud"})
        loc, project = os.environ["VERTEX_LOCATION"], os.environ["VERTEX_PROJECT"]
        url = (f"https://{loc}-aiplatform.googleapis.com/v1/projects/{project}/locations/{loc}"
               f"/publishers/google/models/{urllib.parse.quote(self.model, safe='')}:generateContent")
        body = {"contents": [{"role": "model" if m["role"] == "assistant" else "user",
                              "parts": [{"text": m["content"]}]} for m in messages],
                "generationConfig": {"temperature": temperature, "maxOutputTokens": max_tokens}}
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}
        status, obj = _guard(self.transport, "POST", url,
                             {"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
                             json.dumps(body).encode(), self.timeout, self.name)
        try:
            text = "".join(p.get("text", "") for p in obj["candidates"][0]["content"]["parts"])
        except (KeyError, IndexError, TypeError):
            raise _response_error(self.name, status, obj)
        out = {"text": text, "model_ref": f"vertex:{self.model}", "seed": seed}
        meta = obj.get("usageMetadata") or {}
        if type(meta.get("promptTokenCount")) is int and type(meta.get("candidatesTokenCount")) is int:
            out["token_usage"] = {"input_tokens": meta["promptTokenCount"],
                                  "output_tokens": meta["candidatesTokenCount"]}
        return out


def cloud_backends() -> list:
    """The cloud backends whose settings are present."""
    return [b for b in (AzureOpenAIBackend(), BedrockBackend(), VertexBackend()) if b.health()]
