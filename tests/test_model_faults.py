"""Falsifiers for the reading of a call that failed.

Hermetic: literal status codes, header dicts and bodies, no network. Every case
here is one where the naive read produces a plausible record rather than an
error. Load-bearing: (1) an error inside a one-element array is invisible to a
reader that expects a dict, so the call reports clean; (2) a number in the body
is not the status line, on two surfaces, in two different ways; (3) running out
of money and going too fast both arrive as 429 and only one of them clears by
waiting; (4) a provider instruction to retry outranks a category inferred from
a number, except where retrying cannot help by construction; (5) a 401 body
prints the key it is complaining about.
"""
from harness import model_faults as mf
from harness.model_dialects import ANTHROPIC, GEMINI, OLLAMA, OPENAI

PROJECT_KEY = "-".join(("sk", "proj", "T3BlbkFJabcdef" + "0123456789ABCDEFGH"))  # fake, built at import


# --- the body is not always an object ----------------------------------------

def test_a_gemini_error_inside_a_one_element_array_is_found_and_flagged():
    """streamGenerateContent without alt=sse wraps the error in a list. A
    reader looking for a dict finds none, reports no error, and a failed call
    enters the record as a success with no output."""
    record = mf.capture(
        status=403, dialect=GEMINI,
        body=[{"error": {"code": 403, "message": "caller lacks permission",
                         "status": "PERMISSION_DENIED"}}])
    assert record["category"] == mf.PERMISSION
    assert record["envelope"] == mf.ARRAY_WRAPPED
    assert record["caveats"] == ["ARRAY_WRAPPED_BODY"]
    assert record["message"] == "caller lacks permission"


def test_a_plain_object_body_carries_no_array_caveat():
    record = mf.capture(status=403, dialect=GEMINI,
                        body={"error": {"message": "no"}})
    assert record["envelope"] == mf.OBJECT
    assert record["caveats"] == []


def test_a_list_of_more_than_one_is_not_unwrapped():
    """The unwrap is for a known one-element shape. Picking the first of many
    would choose one error out of several with no rule for which."""
    assert mf.error_body([{"error": {"message": "a"}},
                          {"error": {"message": "b"}}]) is None


def test_a_body_with_no_error_member_reads_as_no_error():
    for body in ({"ok": True}, {}, None, "error", 7, [], {"error": 7}):
        assert mf.error_body(body) is None


# --- one server, two envelopes -----------------------------------------------

def test_a_local_ollama_error_is_a_bare_string_with_no_relayed_status():
    record = mf.capture(status=404, dialect=OLLAMA,
                        body={"error": "model 'qwen3:8b' not found"})
    assert record["shape"] == mf.BARE_STRING
    assert record["category"] == mf.NOT_FOUND
    assert record["upstream_status"] is None
    assert record["caveats"] == []


def test_a_relayed_ollama_error_surfaces_the_status_the_host_actually_sent():
    """The cloud branch relays an upstream status this server never generates
    on its own, 429 among them. Reading only the transport status would report
    a local failure for a remote rate limit and retry it straight away."""
    record = mf.capture(
        status=429, dialect=OLLAMA,
        body={"StatusCode": 429, "Status": "429 Too Many Requests",
              "error": "upstream rate limit"})
    assert record["shape"] == mf.RELAYED
    assert record["upstream_status"] == 429
    assert record["upstream_reason"] == "429 Too Many Requests"
    assert record["category"] == mf.RATE_LIMIT
    assert record["retriable"] is True
    assert "OLLAMA_RELAYED_UPSTREAM_STATUS" in record["caveats"]


def test_a_string_error_without_an_integer_statuscode_is_not_called_relayed():
    record = mf.capture(status=500, dialect=OLLAMA,
                        body={"StatusCode": "429", "error": "x"})
    assert record["shape"] == mf.BARE_STRING
    assert record["upstream_status"] is None


# --- the status line is not always the status --------------------------------

def test_an_openrouter_call_carries_the_caveat_that_its_code_is_not_the_status():
    """Documented: error.code equals the HTTP status only for an invalid
    request or an empty account, and everything else arrives on a 200. A record
    that reports the body code as the status says a live failure succeeded."""
    record = mf.capture(status=200, kind="openrouter", dialect=OPENAI,
                        body={"error": {"code": 429, "message": "throttled"}})
    assert record["status"] == 200
    assert record["body_code"] == 429
    assert record["caveats"] == ["OPENROUTER_CODE_IS_NOT_THE_STATUS_LINE"]


def test_a_top_level_status_integer_is_recorded_beside_the_transport_status():
    """Some 401 bodies carry a status sibling next to error. It agrees with the
    transport here and will not always, so both are kept and neither is read as
    the other."""
    record = mf.capture(
        status=401, dialect=OPENAI,
        body={"status": 401,
              "error": {"message": "Incorrect API key provided",
                        "type": "invalid_request_error",
                        "code": "invalid_api_key"}})
    assert record["status"] == 401
    assert record["body_status"] == 401
    assert record["category"] == mf.AUTH


def test_the_other_openai_401_envelope_reads_the_same_category():
    record = mf.capture(
        status=401, dialect=OPENAI,
        body={"error": {"message": "You didn't provide an API key.",
                        "type": "invalid_request_error", "param": None,
                        "code": None}})
    assert record["category"] == mf.AUTH
    assert record["body_status"] is None
    assert record["retriable"] is False


# --- pace and spend both arrive as 429 ---------------------------------------

def test_running_out_of_money_is_terminal_and_going_too_fast_is_not():
    """Same status, opposite remedy. A client that retries an exhausted account
    burns its backoff budget on a call that cannot succeed until somebody
    pays."""
    quota = mf.capture(status=429, dialect=OPENAI,
                       body={"error": {"code": "insufficient_quota",
                                       "message": "exceeded your quota"}})
    assert quota["category"] == mf.QUOTA
    assert quota["retriable"] is False
    pace = mf.capture(status=429, dialect=OPENAI,
                      body={"error": {"code": "rate_limit_exceeded"}})
    assert pace["category"] == mf.RATE_LIMIT
    assert pace["retriable"] is True


def test_an_unrecognized_429_stays_a_rate_limit_rather_than_a_guess():
    """The spend marker set is narrow on purpose. Promoting an unknown 429 to
    terminal would invent a verdict, and the invented verdict is the expensive
    direction: a transient limit reported as permanent stops the work."""
    record = mf.capture(status=429, dialect=OPENAI,
                        body={"error": {"code": "something_new"}})
    assert record["category"] == mf.RATE_LIMIT


def test_a_context_overflow_is_terminal_whatever_status_it_arrives_on():
    record = mf.capture(status=400, dialect=OPENAI,
                        body={"error": {"code": "context_length_exceeded"}})
    assert record["category"] == mf.TOO_LARGE
    assert record["retriable"] is False


def test_a_mark_is_read_from_whichever_field_the_vendor_used():
    for field in ("type", "code", "error_type", "status"):
        record = mf.capture(status=500, dialect=OPENAI,
                            body={"error": {field: "insufficient_quota"}})
        assert record["category"] == mf.QUOTA


# --- the provider instruction ------------------------------------------------

def test_an_explicit_instruction_not_to_retry_overrides_the_category():
    """Anthropic sends x-should-retry and its own client reads it before any
    status test. A category inferred from a number is a default, and an
    instruction from the server that produced the number outranks it."""
    record = mf.capture(status=409, dialect=ANTHROPIC,
                        headers={"x-should-retry": "false"},
                        body={"error": {"message": "conflict"}})
    assert record["category"] == mf.CONFLICT
    assert record["retriable"] is False
    assert record["retriable_source"] == "provider_header"
    assert record["provider_said_retry"] is False


def test_an_explicit_instruction_to_retry_overrides_in_the_other_direction():
    record = mf.capture(status=400, dialect=ANTHROPIC,
                        headers={"X-Should-Retry": "true"},
                        body={"error": {"message": "transient"}})
    assert record["retriable"] is True
    assert record["retriable_source"] == "provider_header"


def test_a_conflict_with_no_instruction_stays_undecided():
    """Three-state. The vendor client retries 409 by default and the vendor
    error page says to resolve the conflict first, so this layer reports that
    it does not know rather than picking a side."""
    record = mf.capture(status=409, dialect=ANTHROPIC,
                        body={"error": {"message": "conflict"}})
    assert record["retriable"] is None
    assert record["retriable_source"] == "category"
    assert record["provider_said_retry"] is None


def test_the_instruction_does_not_override_a_failure_retrying_cannot_fix():
    """A bad key is a bad key on the second call too. Honoring a retry header
    here would spin on a credential that will not become valid."""
    for status, category in ((401, mf.AUTH), (403, mf.PERMISSION),
                             (402, mf.QUOTA)):
        record = mf.capture(status=status, dialect=ANTHROPIC,
                            headers={"x-should-retry": "true"},
                            body={"error": {"message": "no"}})
        assert record["category"] == category
        assert record["retriable"] is False
        assert record["retriable_source"] == "category"
        assert record["provider_said_retry"] is True


def test_an_unreadable_should_retry_value_is_no_instruction_at_all():
    for value in ("maybe", "", "1", None, 1):
        assert mf.should_retry_header({"x-should-retry": value}) is None
    for junk in (None, [], "x-should-retry: true"):
        assert mf.should_retry_header(junk) is None


# --- the transport changes what a status means -------------------------------

def test_an_unrecognized_400_on_a_websocket_is_unknown_rather_than_terminal():
    """Every realtime example carries status 400 with type
    invalid_request_error, including conditions whose documented remedy is to
    reconnect. Calling that terminal closes a session that should reopen."""
    assert mf.classify(400, None, transport="websocket") == mf.UNKNOWN
    assert mf.classify(400, None) == mf.INVALID_REQUEST


def test_a_known_mark_still_decides_on_a_websocket():
    record = mf.capture(status=400, transport="websocket", dialect=OPENAI,
                        body={"error": {"code": "invalid_api_key"}})
    assert record["category"] == mf.AUTH


def test_a_call_that_never_reached_a_server_is_transport_and_undecided():
    """No status and no body. Whether the request was applied is unknown, so
    whether retrying is safe is the caller risk to weigh."""
    record = mf.capture(dialect=OPENAI)
    assert record["category"] == mf.TRANSPORT
    assert record["retriable"] is None
    assert record["status"] is None


def test_a_body_with_no_status_is_unknown_rather_than_transport():
    """Something answered. Calling it a transport failure would claim the
    request never arrived, which is a different fact."""
    assert mf.classify(None, {"fields": {}}) == mf.UNKNOWN


def test_an_unmapped_status_falls_back_by_class_and_then_to_unknown():
    assert mf.classify(599, None) == mf.SERVER_ERROR
    assert mf.classify(418, None) == mf.UNKNOWN
    assert mf.RETRIABLE[mf.UNKNOWN] is None


# --- what reaches the record -------------------------------------------------

def test_a_live_key_printed_in_a_401_body_never_reaches_the_record():
    """The message says Incorrect API key provided and then prints the key, so
    a durable fault record built from it holds the credential it documents."""
    record = mf.capture(
        status=401, dialect=OPENAI,
        body={"error": {"message": "Incorrect API key provided: " + PROJECT_KEY,
                        "code": "invalid_api_key"}})
    assert PROJECT_KEY not in record["message"]
    assert record["redacted"] is True
    assert record["redacted_kinds"] == ["openai_project_key"]


def test_a_key_nested_in_the_fields_is_scrubbed_too():
    """A router hands back an upstream body under error.metadata, and a key in
    there is as live as one in the message."""
    record = mf.capture(
        status=401, kind="openrouter", dialect=OPENAI,
        body={"error": {"message": "upstream refused",
                        "metadata": {"raw": "bad key " + PROJECT_KEY}}})
    assert PROJECT_KEY not in repr(record["fields"])


def test_the_deadline_rows_travel_with_the_fault():
    record = mf.capture(status=429, dialect=OPENAI,
                        headers={"retry-after": "56",
                                 "x-ratelimit-reset-tokens": "6m0s"},
                        body={"error": {"code": "rate_limit_exceeded"}})
    reads = {r["header"]: r.get("seconds") for r in record["deadlines"]}
    assert reads == {"retry-after": 56.0, "x-ratelimit-reset-tokens": 360.0}


def test_a_record_names_the_dialect_and_kind_it_was_read_under():
    record = mf.capture(status=500, dialect=OPENAI, kind="vllm",
                        body={"error": {"message": "boom"}})
    assert record["dialect"] == OPENAI
    assert record["kind"] == "vllm"
    assert record["transport"] == "http"
    record = mf.capture(status=500)
    assert record["dialect"] is None
    assert record["kind"] is None
