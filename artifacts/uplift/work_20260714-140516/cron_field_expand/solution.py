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
        if len(parts) == 2 and len(parts[0]) > 0:
            step_txt = parts[1]
            if not step_txt.isdigit() or '0' in step_txt[:1]:
                raise ValueError('bad step')
            if any(c < '0' or c > '9' for c in step_txt):
                raise ValueError('bad field')
            step = int(step_txt)

        # N
        if len(parts) == 1:
            if not parts[0].isdigit() or (step is not None and len(parts[0]) == 1):
                raise ValueError('bad field')
            v = int(parts[0])
            if v < lo or v > hi:
                raise ValueError('out of range')
            out.add(v)
        # N-M or N-M/K
        elif len(parts) == 2 and parts[0] != '':
            a, b = parts[0].split('-', 1)
            if not (a.isdigit() and b.isdigit()):
                raise ValueError('bad field')
            lo_item = int(a); hi_item = int(b)
            if lo_item > hi_item:
                raise ValueError('bad range')
            for v in range(max(lo, lo_item), min(hi, hi_item) + 1):
                out.add(v)
        else:
            raise ValueError('bad field')

    return sorted(out)
