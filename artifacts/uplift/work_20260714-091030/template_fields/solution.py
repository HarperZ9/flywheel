from __future__ import annotations


def parse_template_fields(s: str) -> list[tuple[str, str]]:
    n = len(s)
    i = 0
    out: list[tuple[str, str]] = []
    text: list[str] = []

    def emit_text():
        if text:
            chunk = "".join(text)
            text.clear()
            if chunk:
                out.append(("text", chunk))

    while i < n:
        if s[i : i + 2] == "{{":
            i += 2
            text.append("{")
        elif s[i : i + 2] == "}}":
            i += 2
            text.append("}")
        elif s[i] == "{":
            emit_text()
            j = i + 1
            while j < n and s[j] != "}":
                if not (s[j].isascii() and (s[j].isalnum() or s[j] == "_")):
                    raise ValueError(f"invalid field name at offset {i}")
                j += 1
            if j == n:
                raise ValueError(f"unterminated field starting at offset {i}")
            if i + 1 == j:
                raise ValueError(f"empty field at offset {i}")
            out.append(("field", s[i + 1 : j]))
            i = j + 1
        elif s[i] == "}":
            raise ValueError(f"stray '}' at offset {i}")
        else:
            text.append(s[i])
            i += 1

    emit_text()
    return out
