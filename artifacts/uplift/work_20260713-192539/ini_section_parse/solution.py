def parse_ini(text):
    if not isinstance(text, str):
        raise ValueError('bad input')

    lines = text.split('\n')
    result = {}
    sections = {}

    for line in lines:
        line = line.strip()
        
        if not line or line.startswith('#') or line.startswith(';'):
            continue
        
        if line.startswith(['[', '[ ']):
            # Handle section headers
            if line.endswith(']'):
                key, value = line[1:-1].split('=')
                sections[key] = result.setdefault(key, {})
                continue
            
            raise ValueError('bad section')
        
        if not lines or any(line.startswith(key + '=') for key in sections.keys()):
            raise ValueError('no section')
        
        try:
            key, value = line.split('=', 1)
        except ValueError:
            # No equals sign found -> ValueError
            continue
        
        key = key.strip()
        value = value.strip()

        if not all(c in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_'
                   for c in key):
            raise ValueError('bad line')
        
        if sections and any(key in section for section in sections.values()):
            raise ValueError('duplicate key')

        if key not in sections:
            sections[key] = result.setdefault(key, {})
            
        try:
            sections[key][key] = value
        except TypeError:
            # Duplicate key within the same section -> ValueError
            raise ValueError('duplicate key')
    
    return sections
