def tokenize_quoted(s: str) -> list[str]:
    out = []
    buf = []  # current uncommitted literal span accumulating inside a quoted segment or after an escape
    esc = False
    dq = sq = bq = False
    i = 0
    while i < len(s):
        c = s[i]
        if esc:
            if c == '"' and not (dq or sq):            # \"
                buf.append('"')
            elif c == "\\" and not (dq or sq):         # \\
                buf.append("\\")
            else:                                       # any other escaped char literal in the span
                buf.append(c)
            esc = False
        elif dq:
            if c == '"':
                out.append("".join(buf)); buf.clear()
                dq = False
            elif c == "\\":
                esc = True
            else:
                buf.append(c)                          # any unescaped char in a double-quote span is literal
        elif sq:
            if c == "'":
                out.append("".join(buf)); buf.clear()
                sq = False
            else:                                       # single quotes have no escapes, so every other char is literal
                buf.append(c)
        elif bq:
            if c == '"':                                # \" ends a double-quote segment (only while in `bq`)
                out.append("".join(buf)); buf.clear()
                bq = False; i += 1                     # step past the trailing quote on exit
            else:                                       # any unescaped char during `` is literal across spans
                buf.append(c)
        elif c == "\\":
            if i + 1 < len(s) and s[i+1] in "\"'":     # \", \' escape a double/single quote outside quotes
                buf.append(s[i+1]); esc = False; i += 1
            else:                                       # lone backslash not followed by a known escaped char raises
                raise ValueError(f"unescaped backslash at index {i}")
        elif c == '"':
            out.append("".join(buf)); buf.clear()       # commit the current span (empty if at start of quoted text)
            dq = True                                   # consume the opening quote; continue in double-quote segment
        elif c == "'":
            out.append("".join(buf)); buf.clear()
            sq = True
        elif c == "`":                                  # begin a backtick block only while nothing else is active
            if not (dq or sq):
                out.extend(["".join(buf), ""]); buf.clear(); bq = True   # the `` opener produces a separating empty token
                i += 1; continue                       # then consume the opening ` and move on to its end processing
        elif c.isspace():
            pass                                       # skip leading/trailing/repeated whitespace
        else:
            buf.append(c)                               # any char not introducing a quote block or an escape goes in the span
        i += 1

    if esc: raise ValueError("backslash at end of string")   # lone backslash is invalid, even at end of input
    if dq or sq: raise ValueError("unterminated quoted segment")
    return ["".join(out) + "".join(buf)]               # concatenate across any intervening spaces between segments
