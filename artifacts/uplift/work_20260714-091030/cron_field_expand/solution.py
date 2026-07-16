def cron_field(field, lo, hi):
    if not isinstance(lo, int) or not isinstance(hi, int) or lo > hi:
        raise ValueError("bad bounds")
    out = set()
    for item in field.split(","):
        if not item:
            raise ValueError("bad field")
        if item == "*":
            out.update(range(lo, hi + 1))
            continue
        step = None
        slash_idx = item.find("/")
        if slash_idx >= 0:
            step_part = item[slash_idx+1:]
            if not step_part or (step_part[0] in "0" and len(step_part) > 1):
                raise ValueError("bad field")
            try:
                step = int(step_part)
            except ValueError:
                raise ValueError("bad field")
            if step <= 0:
                raise ValueError("bad step")
            item = item[:slash_idx]
        parts = item.split("-")
        if len(parts) == 1:
            num_part = parts[0]
            if slash_idx >= 0:
                raise ValueError("bad field")
        elif len(parts) == 2 and parts[1]:
            lo_str, hi_str = parts
            try:
                parsed_lo = int(lo_str)
            except ValueError:
                raise ValueError("bad field")
            try:
                parsed_hi = int(parts[1])
            except ValueError:
                raise ValueError("bad field")
            if (lo_str[0] in "0" and len(lo_str) > 1) or \
               (hi_str[0] in "0" and len(hi_str) > 1):
                raise ValueError("bad field")
        else:
            raise ValueError("bad field")
        try:
            n = int(num_part)
        except ValueError:
            raise ValueError("bad field")
        if step is None:
            if lo <= n <= hi:
                out.add(n)
        elif len(parts) == 2:
            if parsed_hi < parsed_lo or \
               (parsed_lo < lo or parsed_hi > hi):
                return sorted(out)
            for v in range(parsed_lo, parsed_hi + 1, step):
                out.add(v)
    return sorted(out)
