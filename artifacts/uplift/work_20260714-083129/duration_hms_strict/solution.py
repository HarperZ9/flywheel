def parse_duration_strict(s: str) -> int:
    if not s or len(s.strip()) == 0:
        raise ValueError("Invalid input: empty string")
    
    components = []
    for part in s.split('h'):
        m_parts = re.findall(r'(\d+)(m)', part)
        if not m_parts:
            raise ValueError("No valid minutes found: unexpected format")
        
        digits, unit = map(int, re.match(r'^(\d+)([ms])$', '0'.join(m_parts)).groups())
        
        if len(components) > 0 and (unit == 'm' or unit == 's') and digits > 59:
            raise ValueError("Each component after the first whose unit is 'm' or 's' must be at most 59")
        
        components.append({'digits': digits, 'unit': unit})
    
    if len(components) != 1 and len(s.split('h')) > 2:
        raise ValueError("Too many components: more than one hour component found in the string")
    
    for i, comp in enumerate(reversed(components)):
        total_seconds = (len(components) - i - 1) * 3600 + comp['digits'] * 60
        if total_seconds > 59:
            raise ValueError("Invalid duration: sum of seconds exceeded the valid range")
    
    return sum(comp['digits'] for comp in components) * 60 * (len(components) - 1)
