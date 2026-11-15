"""Linear-time masking of URLs, e-mail addresses, HTML tags, and quoted speech.

The detector blanks these spans with equal-length spaces before the prose passes
run. It used to call re.sub with the reference patterns below. Those patterns
backtrack quadratically on a long line where a match never completes: a run of
"1.1.1.1." or "twenty-twenty-" with no "@", a line of unclosed "<", or a line of
unclosed curly quotes. One such line cost seconds per pass, and strip_markup runs
as many as six times on every line.

Each function here returns exactly the string that re.sub(pattern, blank, line)
returns for its reference pattern, on every input, and runs in linear time. The
findings therefore do not change. tests/test_masking.py checks the equivalence
against the reference patterns on generated input. Standard library only.
"""
import re

# The reference patterns: the definition of record for what each mask blanks.
# The detector compiles them as detector.URL, detector.TAG, and detector.QUOTED,
# and it never calls .sub with them on document text.
URL_PATTERN = r"https?://\S+|\b[\w.-]+@[\w.-]+\.\w+\b"
TAG_PATTERN = r"<[^>]+>"
QUOTED_PATTERN = "\"[^\"\\n]*\"|\u201c[^\u201d\\n]*\u201d|\u2018[^\u2019\\n]*\u2019"

_TAG = re.compile(TAG_PATTERN)
_WEB = re.compile(r"https?://\S+")
_WEB_START = re.compile(r"https?://\S")
_NON_SPACE = re.compile(r"\S*")
_RUN = re.compile(r"[\w.-]+")
_BOUNDARY = re.compile(r"\b")
_DOMAIN = re.compile(r"[\w.-]+\.\w+\b")
_QUOTE_OPEN = re.compile("[\"\u201c\u2018]")
_QUOTE_CLOSE = {"\"": "\"", "\u201c": "\u201d", "\u2018": "\u2019"}


def _blank(m):
    return " " * (m.end() - m.start())


def blank_spans(line, spans):
    """Replace each (start, end) span with the same number of spaces. The spans
    must be sorted and must not overlap."""
    if not spans:
        return line
    parts, prev = [], 0
    for start, end in spans:
        parts.append(line[prev:start])
        parts.append(" " * (end - start))
        prev = end
    parts.append(line[prev:])
    return "".join(parts)


def _next_email(line, pos):
    """The leftmost match of the e-mail alternative of URL_PATTERN that starts at
    or after pos, as (start, end), or None.

    The local part [\\w.-]+ cannot contain "@", so a match must run to the end of
    the [\\w.-] run it starts in, and the "@" must sit right after that run. The
    domain part then depends only on that "@". So every start inside one run
    succeeds or fails together, and the leftmost success is the first word
    boundary in the run. The regex engine retries each boundary in the run and
    rescans the rest of the run each time, which is where the quadratic cost
    came from. This tests each run once."""
    n = len(line)
    while pos < n:
        run = _RUN.search(line, pos)
        if run is None:
            return None
        r0, r1 = run.span()
        if r1 < n and line[r1] == "@":
            # endpos=r1 bounds the scan to this run. A boundary at r1 itself is
            # not a valid start, because the local part needs one character.
            start = _BOUNDARY.search(line, r0, r1)
            if start is not None and start.start() < r1:
                domain = _DOMAIN.match(line, r1 + 1)
                if domain is not None:
                    return start.start(), domain.end()
        pos = r1 + 1
    return None


def url_spans(line):
    """The spans re.sub(URL_PATTERN, ...) replaces, in order, in linear time.

    re.sub scans left to right and takes the leftmost match; at one position the
    web alternative is tried before the e-mail alternative. This keeps the next
    candidate of each alternative and takes the earlier one. A candidate that a
    taken match has passed over is searched again from the new position."""
    n = len(line)
    none = (n + 1, n + 1)
    spans, pos = [], 0
    web = mail = None
    while pos < n:
        if web is None or web < pos:
            m = _WEB_START.search(line, pos)
            web = m.start() if m else n + 1
        if mail is None or mail[0] < pos:
            mail = _next_email(line, pos) or none
        if web > n and mail[0] > n:
            break
        if web <= mail[0]:
            spans.append((web, _NON_SPACE.match(line, web).end()))
        else:
            spans.append(mail)
        pos = spans[-1][1]
    return spans


def mask_urls(line):
    """Blank URLs and e-mail addresses, exactly as re.sub(URL_PATTERN) does."""
    if "@" not in line:
        # With no "@" the e-mail alternative cannot match. The web alternative
        # alone never backtracks, so the regex engine runs it in linear time.
        return _WEB.sub(_blank, line)
    return blank_spans(line, url_spans(line))


def mask_tags(line):
    """Blank HTML tags, exactly as re.sub(TAG_PATTERN) does, in linear time.

    A tag match ends at a ">", so no match can start after the last ">" in the
    line. Before it, every "<" either closes at the first ">" that follows it or
    fails at once on "<>", so the regex never backtracks. Only the part after
    the last ">" made the reference pattern quadratic, and it holds no match."""
    cut = line.rfind(">") + 1
    if cut == 0:
        return line
    return _TAG.sub(_blank, line[:cut]) + line[cut:]


def quote_spans(line):
    """The spans re.sub(QUOTED_PATTERN, ...) replaces, in order, in linear time.

    Each alternative starts with its own opening mark and runs to the first
    closing mark, with no newline between. When an opening mark finds no closing
    mark before the next newline, no later opening mark of the same kind before
    that newline can close either, so the scan skips them. The reference pattern
    retried each one and rescanned to the newline every time."""
    n = len(line)
    spans, pos, stop = [], 0, -1
    dead = {}   # opening mark -> index of the newline before which it cannot close
    while True:
        m = _QUOTE_OPEN.search(line, pos)
        if m is None:
            return spans
        start, mark = m.start(), m.group()
        if dead.get(mark, -1) > start:
            pos = start + 1
            continue
        if stop <= start:   # find the first newline after start, once per line
            stop = line.find("\n", start + 1)
            stop = n if stop < 0 else stop
        close = line.find(_QUOTE_CLOSE[mark], start + 1, stop)
        if close < 0:
            dead[mark] = stop
            pos = start + 1
            continue
        spans.append((start, close + 1))
        pos = close + 1


def mask_quoted(line):
    """Blank quoted spans, exactly as re.sub(QUOTED_PATTERN) does."""
    return blank_spans(line, quote_spans(line))
