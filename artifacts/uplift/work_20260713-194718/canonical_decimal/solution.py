def canonical_decimal(s: str) -> str:
    # Check if input is None or empty string, raise ValueError
    if not s:
        raise ValueError("Input cannot be None or empty")

    # Split the input into sign and rest, handle leading +
    pos_or_neg, rest = next((i, j) for i, j in [(s[0], s[1:]), (None, s)] if j)
    
    # Remove underscores and validate digits
    valid_rest = ''.join(i for i, is_sep in zip(rest, '_' in rest) if not i.isspace() and not i.isdigit() or (i == '.' and not any(j.isdigit() or j == '.' for j in rest[1:])))

    # Validate the input according to rules (not implemented here as they are complex)
    if valid_rest:
        raise ValueError("Invalid decimal format")

    # Process and return the canonical form
    result = ''
    
    integer_part, fraction_part = pos_or_neg == '-', '.' in valid_rest

    if not integer_part and not fraction_part and pos_or_neg == '-':
        result += '-'
    elif not (integer_part or fraction_part):
        raise ValueError("Input must contain at least one digit")

    if integer_part:
        # Remove leading zeros
        integer_part = next((i for i in valid_rest.split('.')[0] if i.isdigit()), '0')
        if integer_part == '.':
            result += '0'
        elif not integer_part:
            result += '0'

    if fraction_part and '.' in valid_rest:
        # Strip trailing zeros from the fraction part
        fraction_part = next((i for i, is_sep in zip(valid_rest.split('.')[1].split('_'), '_' in valid_rest) if (not i.isdigit() or not any(j.isnumeric() or j == '.' for j in valid_rest[valid_rest.index('.')+1:]))), '')

    result += integer_part
    if fraction_part != '':
        result += fraction_part

    return result
