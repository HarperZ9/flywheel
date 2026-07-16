def parse_ini(text):
    def validate_key(key):
        if not (key.isalnum() or key[0] == '_' and all(c.isalnum() or c == '_' for c in key[1:])):
            raise ValueError('bad line')

    sections = {}
    lines = text.split('\n')
    
    for i, line in enumerate(lines):
        stripped_line = line.strip()
        
        if not stripped_line:
            continue

        if stripped_line.startswith(';') or stripped_line.startswith('#'):
            continue

        if stripped_line[0] == '[' and stripped_line[-1] == ']':
            section_name = stripped_line[1:-1]
            
            try:
                validate_key(section_name)
            except ValueError as e:
                raise ValueError('bad section') from e
            
            if section_name in sections:
                raise ValueError('duplicate section')
            
            sections[section_name] = {}
        elif i == 0 and stripped_line != '':
            raise ValueError('no section')

        else:
            try:
                key, value = tuple(stripped_line.split('=', 1))
            except ValueError as e:
                validate_key(stripped_line)
                raise ValueError('bad line') from e
            
            try:
                validate_key(key)
            except ValueError as e:
                raise ValueError('bad line') from e

            sections[section_name][key] = value.strip()

    return sections
