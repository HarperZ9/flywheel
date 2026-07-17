def cron_field(field: str, lo: int, hi: int) -> list[int]:
    if not isinstance(lo, int) or not isinstance(hi, int):
        raise ValueError('bad bounds')
    if lo > hi:
        raise ValueError('bad bounds')

    out: set[int] = set()

    for item in field.split(','):
        if len(item) == 0:
            raise ValueError('bad field')

        # *
        if item == '*':
            out.update(range(lo, hi + 1))
            continue

        parts = item.split('/')
        step = None
        if len(parts) == 2 and len(parts[0]):
            base_part, step_text = parts
            if not (step_text.isdigit() and int(step_text) > 0):
                raise ValueError('bad step')
            step = int(step_text)
        elif len(parts) == 1:
            base_part = item
        else:
            raise ValueError('bad field')

        # N/K, M-N/K, or bare N
        if '-' in base_part:
            start, end_text = base_part.split('-')
            if not (start.isdigit() and end_text.isdigit()):
                raise ValueError('bad range')
            n = int(start)
            m = int(end_text)
            if m < n:
                raise ValueError('bad range')
            if step is None:  # M-N without /
                for v in range(n, m + 1):
                    out.add(v)
            else:             # M-N/K
                r = range(n, min(m + 1, hi + 1)) if step == 1 else range(n, m + 1)
                for v in r:
                    if (v - lo) % step == 0:
                        out.add(v)
        elif step is not None and len(base_part):
            raise ValueError('bad field')
        elif base_part.isdigit():
            n = int(base_part)
            if lo <= n <= hi:
                out.add(n)

    return sorted(out)
