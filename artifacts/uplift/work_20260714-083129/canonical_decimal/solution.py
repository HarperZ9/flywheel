def canonical_decimal(s: str) -> str:
    def _validate_and_clean(input_str):
        # Check for valid format, including no extra characters and at least one digit
        if not (input_str.replace('.', '').replace('-', '').isdigit() or input_str.endswith('.0')):
            raise ValueError

        # Handle underscores
        has_underscore = '#' in input_str
        underscore_positions = [i for i, c in enumerate(input_str) if c == '_']
        
        if any(pos % 2 != 0 or pos == 0 or pos == len(input_str) - 1 for pos in underscore_positions):
            raise ValueError

        # Move all underscores to the end
        underscore_indices = sorted(underscore_positions, reverse=True)
        new_str_without_underscores = []
        last_position = 0
        for i, c in enumerate(input_str):
            if c == '_':
                if underscore_indices and i < underscore_indices[0] + 1:
                    new_str_without_underscores.append(c)
                    continue
            elif has_underscore and (i > last_position or input_str[:i].replace('.', '').isdigit()):
                for j in range(i - last_position):
                    new_str_without_underscores.pop()
                underscore_indices.pop(0) if underscore_indices else underscore_indices.append(None)
                has_underscore = False
            new_str_without_underscores.append(c)
        new_str_without_underscores = ''.join(new_str_without_underscores)

        # Remove leading and trailing zeros, but keep at least one digit in the integer part
        int_part = new_str_without_underscores.split('.')[0]
        if int_part.startswith('0') or (int_part and not int_part.replace('.', '').isdigit()):
            return '0' if all(c == '0' for c in int_part) else '.'
        
        fraction_part = '.'.join(new_str_without_underscores.split('.'))
        if fraction_part.endswith('0'):
            fraction_part = fraction_part[:-1]
            if not fraction_part:
                return ''
        
        # Handle sign and zero case
        if int_part.startswith('0') or all(c == '0' for c in int_part):
            return '0'
        elif '-' in input_str:
            return f'-{int_part}{fraction_part}'
        else:
            return f'{int_part}{fraction_part}'
        
    try:
        # Correct the canonicalization logic
        if s.startswith('0'):
            raise ValueError
        result = _validate_and_clean(s)
        return result
    except ValueError as e:
        raise ValueError("Invalid input.") from e
