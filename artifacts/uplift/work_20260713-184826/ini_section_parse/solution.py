def parse_ini(text):
    if not isinstance(text, str):
        raise ValueError('bad input')
    
    lines = text.splitlines()
    result = {}
    current_section = None
    
    for line in lines:
        stripped_line = line.strip()
        
        if not stripped_line or stripped_line.startswith(';') or stripped_line.startswith('#'):
            continue
        
        if stripped_line[0] == '[' and stripped_line[-1] == ']':
            section_name = stripped_line[1:-1].strip()
            if not section_name.isalnum() or '_' in section_name:
                raise ValueError('bad section')
            if section_name in result:
                raise ValueError('duplicate section')
            current_section = {}
            result[section_name] = current_section
        elif '=' in stripped_line:
            key, value = stripped_line.split('=', 1)
            key = key.strip()
            value = value.strip()
            
            if not key.isalnum() or '_' in key or not key:
                raise ValueError('bad line')
            if key in current_section:
                raise ValueError('duplicate key')
            
            current_section[key] = value
        else:
            raise ValueError('no section')
    
    return result
