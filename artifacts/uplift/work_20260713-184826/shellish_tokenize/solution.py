def tokenize_quoted(s: str) -> list[str]:
    tokens = []
    i = 0
    n = len(s)
    
    while i < n:
        # Skip leading spaces and tabs
        if s[i].isspace():
            i += 1
            continue
        
        # Check for double-quoted segments
        if s[i] == '"':
            start = i + 1
            i += 1
            
            # Consume escaped characters and check for unterminated quote
            while i < n:
                c = s[i]
                if c == '"':
                    if i > start and s[i-1] != '\\':
                        break
                    elif i == start and (i+1 == n or not s[i+1].isspace()):
                        raise ValueError("Unterminated double-quoted segment")
                    i += 1
                    continue
                
                if c == '\\':
                    if i+1 < n:
                        i += 1
                        if s[i] != '"':
                            raise ValueError(f"Invalid escape sequence: {s[i]}")
                        i += 1
                    
                i += 1
            
            # Add the segment to tokens, preserving internal spaces and tabs
            tokens.append(s[start:i])
        
        # Check for single-quoted segments
        elif s[i] == "'":
            start = i + 1
            i += 1
            
            while i < n:
                c = s[i]
                if c == "'":
                    break
                i += 1
            
            # Add the segment to tokens, preserving internal characters
            tokens.append(s[start:i])
        
        # Backslash followed by space/tab/quote
        elif s[i] == '\\':
            if i + 1 < n:
                i += 1
                if not s[i].isspace():
                    raise ValueError(f"Invalid escape sequence: {s[i]}")
            
        else:
            start = i
            while i < n and not s[i].isspace() and s[i] != '"' and s[i] != "'":
                i += 1
            tokens.append(s[start:i])
        
        # Handle concatenated segments
        if (len(tokens) > 1 and len(tokens[-2]) == 0
                and ((tokens[-1][0] == '"' and not tokens[-1].endswith('"'))
                     or (tokens[-1][0] == "'" and not tokens[-1].endswith("'")))):
            tokens[-2] += tokens.pop(-1)
    
    return tokens if any(tokens) else []
