"""Probe the running serve.py: print the raw model output + the extracted code."""
import json, sys, urllib.request
sys.path.insert(0, "/mnt/c/dev/local-model")
from harness.extract import extract_code

PROMPT = ("Implement the function add(a, b) in solution.py. It must return the "
          "sum of two integers. Output ONLY the function definition.")
body = json.dumps({"prompt": PROMPT,
                   "system": "You are a code generator. Output only executable code.",
                   "max_new_tokens": 200, "temperature": 0.0, "seed": 0}).encode()
req = urllib.request.Request("http://127.0.0.1:8765/generate", data=body,
                             headers={"Content-Type": "application/json"})
with urllib.request.urlopen(req, timeout=300) as r:
    obj = json.loads(r.read())
raw = obj["text"]
print("--- RAW MODEL OUTPUT ---")
print(repr(raw[:600]))
print("--- EXTRACTED CANDIDATE ---")
print(repr(extract_code(raw)))
