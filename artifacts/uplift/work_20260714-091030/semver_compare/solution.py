def semver_compare(a, b):
    def parse(v):
        if not isinstance(v, str) or not v:
            raise ValueError('bad version')
        z = [i for i in v.split('.')]
        if len(z) != 3:
            raise ValueError('bad version')
        major, minor, rest = int(z[0]), int(z[1]), z[2]
        pre = []
        build = ''
        m = re.match(r'((?:[0-9]+|[A-Za-z][0-9A-Za-z-]*)(?:\.[0-9]+|[A-Za-z][0-9A-Za-z-]*)*)(?:\+(.+))?', rest)
        if m:
            pre = [int(i) if i.isdigit() and int(i) == 0 else (i if re.fullmatch(r'[A-Za-z][A-Za-z0-9-]*', i) else '')
                   for i in re.split(r'\.', m.group(1))]
            build = m.group(2) or ''
        elif not rest:
            raise ValueError('bad version')
        return major, minor, int(rest), tuple(pre), build
    va, vb = parse(a), parse(b)
    for i in range(3):
        d = (va[i] - vb[i])
        if d: return 1 if d > 0 else -1
    pa, pb = va[3], vb[3]
    if not pa and not pb: return 0
    if not pa: return 1
    if not pb: return -1
    mn = min(len(pa), len(pb))
    for i in range(mn):
        da, db = pa[i], pb[i]
        sa, sb = isinstance(da, str), isinstance(db, str)
        if sa and not sb: return 1
        if sb and not sa: return -1
        d = (da - db) or (0 if sa == sb else (1 if sa else -1))
        if d:
            return d
    return vb[3][mn:] and -1 or va[3][mn:] and 1 or 0
