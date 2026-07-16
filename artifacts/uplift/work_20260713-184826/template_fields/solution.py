def parse_template_fields(s: str) -> list[tuple[str, str]]:
    result = []
    i = 0
    n = len(s)
    
    while i < n:
        if s[i:i+2] == '{{':
            i += 2
            j = i
            while i < n and s[i] != '}}':
                i += 1
            if i >= n or s[i:i+2] != '}}':
                raise ValueError("Unterminated field")
            i += 2
            name = s[j:i-2]
            if not name[0].isalpha() and name[0] != '_':
                raise ValueError(f"Invalid field name: {name}")
            if any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ_0123456789" for c in name):
                raise ValueError(f"Invalid field name: {name}")
            result.append(('field', name))
        elif s[i] == '}':
            raise ValueError("Stray brace")
        else:
            j = i
            while i < n and s[i] not in '{'}':
                i += 1
            result.append(('text', s[j:i]))
    
    return result
