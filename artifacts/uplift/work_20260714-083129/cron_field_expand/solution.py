def cron_field(field: str, lo: int, hi: int) -> List[int]:
    if not (isinstance(lo, int) and isinstance(hi, int)):
        raise ValueError('bad bounds')
    
    if lo > hi:
        raise ValueError('bad bounds')

    step = None
    duplicates = set()
    ranges = []

    for item in field.split(','):
        # Handle range: N-M
        if '-' in item:
            N, M = map(int, item.split('-'))
            if N > M or not (lo <= N <= hi and lo <= M <= hi):
                raise ValueError('bad range')
            ranges.append(range(N, M + 1))
        
        # Handle step: N-K
        elif '/' in item:
            N, K = map(int, item.split('/'))
            if K < 0 or not (lo <= N <= hi and lo % N == 0):
                raise ValueError('bad field')
            step = N
            ranges.append(range(N, hi + 1, N))
        
        # Handle single value: N
        elif '*' in item:
            duplicates.update(range(lo, hi + 1) if '*' in item else [int(item)])
    
    # Combine and deduplicate the list of ranges
    combined_ranges = set(itertools.chain.from_iterable(ranges))

    return sorted(combined_ranges.intersection(duplicates))
