def unfold_headers(lines: list[str]) -> list[tuple[str, str]]:
    if not lines:
        return []
    
    headers = []
    current_name = None
    name_parts = []

    for line in lines:
        if line.startswith((' ', '\t')):
            if not current_name or not name_parts:
                raise ValueError("First line is a continuation")
            value_parts = [name_parts[-1]]
            for part in line.split():
                if part.strip():
                    value_parts.append(part.strip())
            if value_parts[0]:
                headers.append((current_name.lower(), ' '.join(value_parts)))
        else:
            parts = line.split(':', 1)
            if len(parts) != 2 or not parts[0].strip() or not parts[1].strip():
                raise ValueError("Invalid header format")
            name, value = parts
            name = name.strip().lower()
            if not all(c.isascii() and c in '0123456789abcdefghijkmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ-' for c in name):
                raise ValueError("Invalid name character(s)")
            current_name = name
            name_parts = [name]
    
    return headers
