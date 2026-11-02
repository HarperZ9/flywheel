"""Deterministic privacy and safety gates.

A gate returns a reason string when a unit must not be stored, or None.
Gated units are kept only as stubs: session, offset, kind and reason, so a
reader can see that something was skipped and where, without its text.
"""

import re

_SECRET = re.compile(
    r"(sk-[A-Za-z0-9_-]{20,}|ghp_[A-Za-z0-9]{20,}|gho_[A-Za-z0-9]{20,}"
    r"|github_pat_[A-Za-z0-9_]{20,}|AKIA[0-9A-Z]{16}|xox[abposr]-[A-Za-z0-9-]{10,}"
    r"|-----BEGIN [A-Z ]*PRIVATE KEY-----|Bearer\s+[A-Za-z0-9._~+/-]{24,}"
    r"|(?:password|passwd|api[_-]?key|secret|token)\s*[:=]\s*['\"]?[^\s'\"]{10,})",
    re.IGNORECASE,
)

_KIN = (r"father|mother|dad|mom|mum|sister|brother|wife|husband|girlfriend"
        r"|boyfriend|partner|son|daughter|family|grandma|grandpa|uncle|aunt|cousin")
_LIFE = (r"doctor|therapist|therapy|diagnosis|medication|meds|health|hospital"
         r"|bank account|debt|rent|landlord|lawyer|court case|divorce|salary"
         r"|home address|phone number|ssn|social security")
_PERSONAL = re.compile(
    rf"\b(?:my|your|his|her|our)\s+(?:{_KIN}|{_LIFE})\b"
    r"|\bI\s+(?:was|am|have been|got|had been)\s+(?:diagnosed|abused|hospitali[sz]ed"
    r"|arrested|fired|evicted|assaulted)\b"
    r"|\byou\s+(?:were|are|have been)\s+(?:diagnosed|abused|hospitali[sz]ed)\b",
    re.IGNORECASE,
)
_CONTACT = re.compile(
    r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"
    r"|\+?\d{1,2}[\s.-]?\(?\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}\b"
)
# Addresses that are public by design (git noreply, bot accounts).
_CONTACT_OK = re.compile(r"noreply|no-reply|users\.noreply\.github\.com|example\.(?:com|org)")

_STOPPED_TEXT = re.compile(r"Usage Policy|safety (?:classifier|filter)s? (?:flagged|stopped)",
                           re.IGNORECASE)


def text_gate(text: str) -> str | None:
    """Reason to skip a unit's text, or None when it may be stored."""
    if _SECRET.search(text):
        return "secret"
    if _PERSONAL.search(text):
        return "personal"
    return None


def redact_contacts(text: str) -> tuple[str, int]:
    """Replace e-mail addresses and phone numbers with a marker."""
    count = 0

    def _sub(m):
        nonlocal count
        if _CONTACT_OK.search(m.group(0)):
            return m.group(0)
        count += 1
        return "[contact]"
    return _CONTACT.sub(_sub, text), count


def record_stopped(record: dict) -> bool:
    """True for an assistant record that a safety classifier stopped."""
    if record.get("isApiErrorMessage"):
        return True
    msg = record.get("message") or {}
    if msg.get("stop_reason") == "refusal":
        return True
    content = msg.get("content")
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                if _STOPPED_TEXT.search(block.get("text", "")[:600]):
                    return True
    return False
