def parse_duration_strict(s: str) -> int:
    if not s:
        raise ValueError("Input string cannot be empty")
    
    components = []
    part = ""
    for char in s:
        if char.isdigit() or (char == '-' and part):
            part += char
            continue
        
        # Check for the last digit of a component, which is invalid if it's not 0-9.
        if part:
            if any(part[i] == '-' for i in range(1, len(part))):
                raise ValueError("Invalid duration format")
            if int(part) < 0 or (part and not char.isdigit()):
                raise ValueError("Invalid duration format")
            
            components.append(int(part))
            part = ""
        
        # Check for a unit
        if len(part):
            if not ('h' <= char.lower() <= 's'):
                raise ValueError("Invalid character in the string")
            if char.islower():
                units_map = {'h': 3600, 'm': 60, 's': 1}
                components.append(components[-1] // units_map[char])
                components[-2] %= units_map[char]
        else:
            # The first component can have any value
            if char.lower() not in units_map:
                raise ValueError("Invalid duration format")
    
    if len(components) > 3 or (len(components) == 3 and components[1] != components[0]):
        raise ValueError("Invalid number of components with descending order")
    
    # Check the range rule for the first component
    if len(components) == 1:
        if components[0] >= 60 * units_map[list(units_map.keys())[0]]:
            raise ValueError("Range rule violation")
    
    total_seconds = sum(c * u for c, u in zip(components, [3600, 60, 1]))
    return total_seconds
