def parse_range_list(s: str) -> list:
    if not s.strip():
        return []

    ranges = []
    for token in s.replace(',', ' ').split():
        if '-' in token:
            start, end = map(int, token.split('-'))
            if start > end:
                raise ValueError(f"Malformed range: {token}")
            ranges.append(range(start, end + 1))
        elif token.isdigit():
            ranges.append([int(token)])
        else:
            raise ValueError(f"Malformed token: {token}")

    result = set()
    for r in ranges:
        result.update(r)

    return sorted(result)
