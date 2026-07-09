def parse_range_list(s):
    vals = set()
    s = s.strip()
    if not s:
        return []
    for tok in s.split(','):
        tok = tok.strip()
        if '-' in tok[1:]:
            cut = tok.index('-', 1)
            a, b = tok[:cut], tok[cut + 1:]
            if not a.lstrip('-').isdigit() or not b.lstrip('-').isdigit():
                raise ValueError(tok)
            lo, hi = int(a), int(b)
            if lo > hi:
                raise ValueError(tok)
            vals.update(range(lo, hi + 1))
        else:
            if not tok.lstrip('-').isdigit():
                raise ValueError(tok)
            vals.add(int(tok))
    return sorted(vals)
