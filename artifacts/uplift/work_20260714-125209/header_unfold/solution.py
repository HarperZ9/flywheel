def unfold_headers(lines: list[str]) -> list[tuple[str, str]]:
    if not all(isinstance(line, str) for line in lines):
        raise TypeError("unfold_headers: all elements of `lines` must be strings")
    
    def is_valid_name(s: str) -> bool:
        return s and all(c.isalnum() or c == "-" for c in s)
    
    headers = []
    current_name: str | None = None
    value_parts: list[str] = []
    had_non_ws_continuation = False
    
    for raw_line in lines:
        if not isinstance(raw_line, str):
            raise TypeError("unfold_headers: all elements of `lines` must be strings")
        
        stripped = raw_line.lstrip()
        
        if raw_line == "":
            # Empty line -- continue unfolding (RFC 7230/5322 allow empty headers)
            continue
        
        continuation = stripped.startswith((" ", "\t"))
        colon_pos = stripped.find(":")
        
        if current_name is None:
            if continuation:
                raise ValueError("unfold_headers: physical line starts with whitespace; no preceding header name")
            
            if colon_pos == -1:
                raise ValueError(f"unfold_headers: no colon in header line (empty after stripping): {repr(raw_line)}")
            
            before_colon = stripped[:colon_pos].strip()
            
            # Validate header name -- RFC 7230, 7230#section-3.2: token ABNF,
            #    case-insensitive comparisons; no spaces before/after colon.
            if not is_valid_name(before_colon):
                raise ValueError(
                    f"unfold_headers: invalid header name (non-token): {repr(before_colon)}"
                )
            
            current_name = before_colon.lower()
            value_parts = [stripped[colon_pos + 1 :].strip()]
        else:
            # Continuation of a logical line
            if not continuation:
                raise ValueError("unfold_headers: mixed header lines without continuations")
            
            v_part = stripped[1:].lstrip()  # strip leading WS on the line itself
            
            if v_part and all(c.isspace() for c in v_part):
                had_non_ws_continuation = False
                continue  # purely whitespace continuation -- skip
        
        value_parts.append(v_part)
        had_non_ws_continuation = True
    
    if current_name:
        combined_value = " ".join(value_parts)
        
        headers.append((current_name, combined_value))
    
    return headers
