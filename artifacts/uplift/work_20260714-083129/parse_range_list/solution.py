def parse_range_list(s):
    def to_integers(range_str):
        start, end = None, None
        if '-' in range_str:
            parts = range_str.split('-')
            start = int(parts[0].strip())
            end = int(parts[1].strip()) + 1  # Inclusive end of the range
        else:
            return [int(range_str.strip())]
        if start > end or (end - start) < 1:
            raise ValueError(f"Invalid range: '{range_str}'")
        return list(range(start, end))
    
    tokens = s.replace(' ', '').split(',')
    result = []
    for token in tokens:
        try:
            integers = to_integers(token.strip())
            result.extend(integers)
        except Exception as e:
            raise ValueError(f"Malformed token: '{token}'") from e
    return sorted(set(result))
