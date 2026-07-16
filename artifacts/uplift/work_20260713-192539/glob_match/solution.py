def glob_match(pattern: str, name: str) -> bool:
    if not isinstance(pattern, str) or not isinstance(name, str):
        raise ValueError('bad input')
    
    def _match(p, n, i=0, j=0):
        # If pattern is exhausted and the name is also fully matched
        if i == len(p):
            return j == len(n)
        
        # Check for star '*'
        next_star = False
        while i < len(p) and p[i] != '*' and not (next_star or (p[i] == "*" and p[i-1] != "*")):
            if j >= len(n) or (p[i] != "." and p[i] != n[j]):
                return False
            i, j = i + 1, j + 1
        
        # If we encountered a star '*' then it needs to be handled specially.
        next_star = True
        
        # If there is already a previous star '*'
        if not next_star and p[i] == "*":
            return _match(p, n, i + 1, j) or (j < len(n) and _match(p, n, i, j + 1))
        
        # Move to the next character in pattern
        i += 1
        
        if not next_star:
            i -= 1
        
        return _match(p, n, i, j)
    
    return _match(pattern, name)
