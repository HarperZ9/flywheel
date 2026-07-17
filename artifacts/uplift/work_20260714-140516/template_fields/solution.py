def parse_template_fields(s: str) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    i = 0
    n = len(s)
    text_buf: list[str] = []

    def emit_text():
        nonlocal text_buf
        if text_buf:
            chunk = "".join(text_buf)
            # Merge consecutive text chunks and prevent empty chunks.
            if not out or out[-1][0] != "text":
                out.append(("text", chunk))
            else:
                out[-1] = ("text", out[-1][1] + chunk)
            text_buf = []

    while i < n:
        if s.startswith("{{", i):
            emit_text()
            out.append(("text", "{"))
            i += 2
        elif s.startswith("}}", i):
            emit_text()
            out.append(("text", "}"))
            i += 2
        elif s[i] == "{":
            emit_text()
            brace_end = s.find("}", i + 1)
            if brace_end < 0:
                raise ValueError("unterminated field")
            name = s[i + 1 : brace_end]
            if not name or not name[0].isalpha() and name[0] != "_":
                raise ValueError(f"invalid field name: {name!r}")
            for c in name[1:]:
                if not (c.isalnum() or c == "_"):
                    raise ValueError(f"invalid field name: {name!r}")
            out.append(("field", name))
            i = brace_end + 1
        elif s[i] == "}":
            emit_text()
            # A lone '}' that does not terminate a field is a stray brace.
            if i < n and s.startswith("}", i):
                raise ValueError("stray brace")
        else:
            text_buf.append(s[i])
            i += 1

    emit_text()
    return out
