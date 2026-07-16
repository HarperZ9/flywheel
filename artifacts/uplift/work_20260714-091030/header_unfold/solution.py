def unfold_headers(lines: list[str]) -> list[tuple[str, str]]:
    if not lines:
        return []

    out = []
    name: str | None = None
    pieces: list[str] = []

    for line in lines:
        stripped = line.strip()
        if stripped and (stripped[0] == " " or stripped[0] == "\t"):
            if name is None:
                raise ValueError("physical line starts with whitespace but no preceding header")
            # continuation
            piece = line.lstrip().strip()
            if not piece:
                raise ValueError("continuation line has only whitespace content")
            pieces.append(piece)
        else:
            if name is not None:
                out.append((name, " ".join(pieces)))
            colon_pos = stripped.find(":")
            if colon_pos == -1 or colon_pos == 0:
                raise ValueError("header lacks a colon or empty name")
            raw_name = stripped[:colon_pos]
            for c in raw_name:
                if not (c.isalnum() or c == "-"):
                    raise ValueError(f"bad header name character: {repr(c)}")
            name = raw_name.lower()
            pieces = [stripped[colon_pos + 1:].strip()]

    if name is not None:
        out.append((name, " ".join(pieces)))

    return out
