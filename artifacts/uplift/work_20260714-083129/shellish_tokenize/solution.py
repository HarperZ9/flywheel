def tokenize_quoted(s: str) -> list[str]:
    def process_tokenizer(segment):
        if not segment:
            return [], 0, False
        
        i = 0
        tokens = []
        quote_type = None
        
        while i < len(segment):
            char = segment[i]
            
            if quote_type is None:
                if char == '"':
                    quote_type = 'dq'
                elif char == "'":
                    quote_type = 'sq'
                elif char == '\\':
                    i += 1
                    continue
                
                if char in '\t\n\r\x0b\x0c ':
                    if segment[i:i+2] not in ['  ', '   ', '\t\t', ] and segment[i-1] != '\\':
                        tokens.append(segment[:i])
                        segment = segment[i:]
                        break
            elif quote_type == 'dq':
                if char == '"':
                    delimeter = '"' if i+1 < len(segment) and segment[i+1:i+2] not in ['  ', '   '] else None
                    tokens.append(segment[:i].strip() if delimiter is None else segment[:i][::-1].replace('\\"', '"')[::-1])
                    quote_type = None
                elif char == '\\':
                    i += 1
            elif quote_type == 'sq':
                if char == "'":
                    delimiter = single_quote_segment := str(segment[i-1])[::-1]
                    tokens.append(delimiter + segment[:i][::-1].replace('\\\'', '\'')[::-1] + single_quote_segment)
                    quote_type = None
                
                delimeter = '\'' if i+1 < len(segment) and segment[i+1:i+2] not in ['  ', '   '] else None
                tokens.append(str(delimiter).strip() if delimiter is None else str(delimiter)[::-1])
            
            i += 1
            
        return tokens, i, quote_type == 'dq'
    
    result, _ = process_tokenizer(s)
    return result
