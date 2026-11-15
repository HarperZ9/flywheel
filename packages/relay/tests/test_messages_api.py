"""Falsifiers for the per-turn receipt (the witnessing contract itself).

The receipt claims to bind request ⊕ prompt ⊕ model ⊕ response into an id a
stranger can re-derive. These pin the honest version of that claim:
  (1) prompt_hash is computed LOCALLY over the prompt we actually sent, so a
      receipt holder can re-derive it; a server-attested hash is recorded beside
      it, never in place of it;
  (2) the requested model tier name is bound into the request hash, so an
      aliasing event (frontier name -> local model) is witnessed;
  (3) the applied seed is recorded only when a backend actually pinned one;
      a tier that cannot pin a seed reports seed=None (non-reproducible), not a
      seed of 0 that would falsely imply a pin;
  (4) stop_reason reflects the backend's finish signal — a length-truncated turn
      is not laundered into a natural end_turn;
  (5) receipt_id re-derives from the stored fields alone.
"""
from relay.messages_api import make_receipt, recompute_receipt_id, translate_response

_REQ = {"prompt": "P", "system": "", "max_new_tokens": 10, "temperature": 0.0,
        "seed": 0, "requested_model": "m"}


def test_prompt_hash_is_local_not_server_attested():
    local = make_receipt(_REQ, {"text": "a"}, "serve")
    served = make_receipt(_REQ, {"text": "a", "prompt_hash": "deadbeef00000000"}, "serve")
    # the server's number does NOT displace the locally computed one
    assert local["prompt_hash"] == served["prompt_hash"]
    assert local["receipt_id"] == served["receipt_id"]        # id binds the sent prompt
    assert served["server_prompt_hash"] == "deadbeef00000000"  # kept, but labeled
    assert served["prompt_hash_match"] is False


def test_requested_model_is_bound_in_the_request_hash():
    base = {k: v for k, v in _REQ.items() if k != "requested_model"}
    a = make_receipt({**base, "requested_model": "claude-opus-4"}, {"text": "x"}, "serve:14b")
    b = make_receipt({**base, "requested_model": "local"}, {"text": "x"}, "serve:14b")
    assert a["request_hash"] != b["request_hash"]             # the requested tier is witnessed


def test_seed_is_null_when_the_backend_did_not_pin_one():
    applied = make_receipt(_REQ, {"text": "x", "seed": 7}, "serve")
    not_applied = make_receipt(_REQ, {"text": "x", "seed": None}, "claude:sonnet")
    assert applied["seed"] == 7
    assert not_applied["seed"] is None                        # hosted tier: non-reproducible


def test_stop_reason_threads_truncation_not_a_fake_end_turn():
    natural = translate_response({"text": "done"}, _REQ, "serve")
    cut = translate_response({"text": "cut off", "stop_reason": "length"}, _REQ, "serve")
    assert natural["stop_reason"] == "end_turn"
    assert cut["stop_reason"] == "max_tokens"                 # length is not end_turn
    assert cut["x_receipt"]["stop_reason"] == "max_tokens"    # and it is witnessed


def test_receipt_id_re_derives_from_stored_fields():
    r = translate_response({"text": "hello"}, _REQ, "serve:14b")["x_receipt"]
    assert recompute_receipt_id(r) == r["receipt_id"]        # a stranger can re-check it
