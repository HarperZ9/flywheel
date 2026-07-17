def parse_template_fields(s: str) -> list[tuple[str, str]]:
    if not s:
        return []
    
    result = []
    current_chunk = ('text', '')
    field_index = 0
    
    for i, char in enumerate(s):
        if current_chunk[0] == 'field':
            if char != '}':
                continue
            # Terminate field
            if result and not s[i:].startswith('}'):
                raise ValueError(f"ValueError: Unterminated field at index {i}")
            field_value = current_chunk[1]
            result.append(current_chunk)
            current_chunk = ('text', '')
            field_index += 1
        elif current_chunk[0] == 'text':
            if char != '{':
                continue
            # Start new or continue existing chunk
            if s[i:].startswith('{{'):
                # Escape brace escape case
                result.append(current_chunk)
                current_chunk = ('text', '')
            else:
                current_chunk = ('field', f'f{field_index}')
        elif current_chunk[0] == 'text':
            if char != '}' or not s[i:].startswith('}}'):
                continue
            # Terminate text chunk
            result.append(current_chunk)
            current_chunk = ('text', '')
    
    if current_chunk[0] == 'field':
        raise ValueError(f"ValueError: Unterminated field at the end of string")
    
    return result
