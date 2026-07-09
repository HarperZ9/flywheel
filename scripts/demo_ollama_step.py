"""Guarded live-generation demo step against a local Ollama endpoint.

Probes the endpoint first. If it is not answering, prints an honest
SKIPPED note and exits 0 so the demo recording stays clean and truthful.
Python 3.12 stdlib only; talks to 127.0.0.1 only.
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request

PROBE_TIMEOUT_SECONDS = 3.0


def probe(url: str) -> str | None:
    """Return the Ollama version string, or None when the endpoint is down."""
    try:
        with urllib.request.urlopen(f"{url}/api/version", timeout=PROBE_TIMEOUT_SECONDS) as response:
            return json.loads(response.read().decode("utf-8", errors="replace")).get("version", "unknown")
    except (urllib.error.URLError, OSError, TimeoutError, ValueError):
        return None


def generate(url: str, *, model: str, prompt: str, num_predict: int, timeout_seconds: float) -> dict:
    body = json.dumps(
        {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {"num_predict": num_predict, "temperature": 0},
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        f"{url}/api/generate", data=body, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        return json.loads(response.read().decode("utf-8", errors="replace"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:11434")
    parser.add_argument("--model", default="flywheel-local-coder-14b")
    parser.add_argument("--prompt", default="def fibonacci(n):")
    parser.add_argument("--num-predict", type=int, default=48)
    parser.add_argument("--timeout-seconds", type=float, default=90.0)
    args = parser.parse_args(argv)

    version = probe(args.url)
    if version is None:
        print(f"SKIPPED: no Ollama endpoint answering at {args.url}")
        print("The rest of this demo still stands on its own; start Ollama and re-record to see the live step.")
        return 0

    print(f"endpoint: {args.url} (ollama {version})")
    print(f"model:    {args.model}")
    print(f"prompt:   {args.prompt!r}  (num_predict={args.num_predict}, temperature=0)")
    started = time.perf_counter()
    try:
        reply = generate(
            args.url,
            model=args.model,
            prompt=args.prompt,
            num_predict=args.num_predict,
            timeout_seconds=args.timeout_seconds,
        )
    except (urllib.error.URLError, OSError, TimeoutError, ValueError) as exc:
        print(f"SKIPPED: endpoint answered the probe but generation failed: {exc}")
        return 0
    elapsed_ms = int(round((time.perf_counter() - started) * 1000))

    print(f"generated in {elapsed_ms} ms")
    print("--- completion ---")
    print(args.prompt + str(reply.get("response", "")))
    print("--- end completion ---")
    eval_count = reply.get("eval_count")
    if isinstance(eval_count, int) and elapsed_ms > 0:
        print(f"tokens: {eval_count} ({eval_count * 1000.0 / elapsed_ms:.1f} tok/s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
