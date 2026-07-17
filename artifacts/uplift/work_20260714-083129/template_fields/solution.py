def parse_template_fields(s: str) -> list[tuple[str, str]]:
    if not s:
        return []
    
    tokens = []
    text_chunk = ''
    field_name = None
    
    for i, char in enumerate(s):
        if char == '{':
            if text_chunk:
                tokens.append(('text', text_chunk))
                text_chunk = ''
                
            if field_name is not None and text_chunk:
                raise ValueError("Field name cannot contain literal braces")
            
            if text_chunk or any(text_chunk.endswith(c) for c in ('}', '}')):
                raise ValueError("Unterminated field found")
            
            tokens.append(('field', field_name))
            field_name = None
        elif char == '}':
            if not text_chunk and field_name:
                raise ValueError("Unmatched closing brace")
            
            if field_name is not None:
                tokens.append(('field', field_name))
                field_name = None
            
            if text_chunk or any(text_chunk.startswith(c) for c in ('{{', '{{')):
                raise ValueError("Stray opening brace found")
            
            tokens.append(('text', text_chunk.replace('{{', '{').replace('}}', '}')))
            text_chunk = ''
        elif char == '{':
            field_name = s[i+1:] if i + 1 < len(s) and (s[i-1] != '{{' or not all(text_chunk.endswith(c) for c in ('}', '}}')) else None
        else:
            text_chunk += char
    
    if text_chunk:
        tokens.append(('text', text_chunk))
    
    return tokens
