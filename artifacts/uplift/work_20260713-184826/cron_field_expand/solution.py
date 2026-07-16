def cron_field(field, lo, hi):
    if not isinstance(lo, int) or not isinstance(hi, int) or lo > hi:
        raise ValueError('bad bounds')

    def expand_range(r, lo, hi):
        a, b = r.split('-')
        start = max(lo, min(int(a), hi))
        end = min(hi, max(int(b), lo))
        if start > end:
            raise ValueError('bad range')
        return set(range(start, end + 1))

    def expand_step(n_k, lo, hi):
        a, b = n_k.split('/')
        step = int(b)
        value = int(a)
        if step == 0:
            raise ValueError('bad step')
        start = max(lo, min(value, hi))
        return set(range(start, hi + 1, step))

    def expand_single_value(v):
        return {int(v)}

    def parse_item(item, lo, hi):
        if item == '*':
            return set(range(lo, hi + 1))
        elif '/' in item:
            return expand_step(item, lo, hi)
        elif '-' in item:
            return expand_range(item, lo, hi)
        else:
            return expand_single_value(item)

    def parse_field(fld):
        items = fld.split(',')
        result = set()
        for item in items:
            if not item or any(c not in '0123456789*/-' for c in item):
                raise ValueError('bad field')
            try:
                result.update(parse_item(item, lo, hi))
            except ValueError as e:
                raise ValueError('bad field') from e
        return sorted(result)

    return parse_field(field)
