import re

def tokenize_quoted(s: str) -> list[str]:
    tokens = []
    
    # First pass: find unquoted spaces/tabs and separate to tokens
    while s.count(' ') or s.count('\t') != 0:
        if ' '.join(re.split(r"([ \t]*)", s, maxsplit=1)) == '':
            break
        
        token = [s[0]]
        first_space_replacement = "\n"
        
        # Second pass: find double-quotes
        for idx, c in enumerate(s):
            if c == "\"":
                if ' '.join(re.split(r"([ \t]*)", s[idx + 1:], maxsplit=1)) == '':
                    break
            
            elif c == '\\':
                first_space_replacement = " ".join(re.split(r"([ \t]*)", s, maxsplit=1)[0])
            
            else:
                if ' '.join(re.split(r"([ \t]*)", s[idx + 1:], maxsplit=1)) != '':
                    token.append(first_space_replacement)
                
                # Handle inside quotes
                elif c == '"':
                    break
                    
                else:
                    token.append(c)
        
        tokens.extend(token)
        
    return tokens
