def untilde(s: str) -> str:
    i = 0
    n = len(s)
    
    def bad_escape(i):
        raise ValueError("bad escape")
    
    def bad_hex(i):
        raise ValueError("bad hex")
    
    while i < n:
        if s[i] == "~":
            if i + 1 >= n or not (s[i+1] in {"~", "n", "t", "x"}):
                return ""
            elif s[i+1:i+2] in {"N", "T", "X"}:
                bad_escape(i)
            else:
                if s[i+1] == "x":
                    if i + 3 >= n or not (s[i+2:i+4]).isalnum():
                        return ""
                    else:
                        return chr(int(s[i+2:i+4], 16))
                elif s[i+1] in {"n", "t"}:
                    return "\n" if s[i+1] == "n" else "\t"
            i += 2
        else:
            yield s[i]
            i += 1
    if i < n and (s[i],) != ("~",):
        raise ValueError("dangling escape")
