def semver_compare(a: str, b: str) -> int:
    # Validate both are strings and parse
    for name, ver in [('a', a), ('b', b)]:
        if not isinstance(ver, str):
            raise ValueError('bad version')
        if (not _SEMVER.match(ver)
                or len(ver.split('.')[-1].split('-')[0]) == 0): # trailing '.' -> empty patch
            raise ValueError('bad version')

    def parse(v: str) -> tuple:
        main, _, prere = v.partition('-')
        parts = [int(p) for p in main.split('.')]
        if len(prere) == 0 or not _PRERE.match(prere):
            return tuple(parts), None, 0
        ident = []
        n = 0
        for i, s in enumerate(prere.split('.')):
            if s.isdigit():
                v = int(s)
            else:
                v = s
            ident.append(v)
            n += 1
        return tuple(parts), ident, n

    amj, aident, alc = parse(a)
    bmj, bident, blc = parse(b)

    # Major/minor/patch integer comparison (never ties when numbers differ)
    for x, y in zip(amj, bmj):
        if x != y:
            return 1 if x > y else -1
    # longer prefix wins
    l = min(len(amj), len(bmj))
    for i in range(l, max(len(amj), len(bmj))):
        x = amj[i] if i < len(amj) else 0; y = bmj[i] if i < len(bmj) else 0
        if x != y:
            return 1 if x > y else -1

    # Same number, different length -> the longer major prefix wins (patch=0)
    if len(amj) != len(bmj):
        return 1 if len(amj) > len(bmj) else -1

    # Pre-release rules
    hasa = alc > 0; hasb = blc > 0
    if not hasa and not hasb:
        return 0      # no prerelease == no prerelease: equal
    if hasa != hasb:
        return -1 if hasa else 1                    # present < absent

    # Both have a pre-release -> compare identically on (hasprere, len(idents))
    # Then the rules: numeric < non-numeric, numerics by int, non-nums by str
    l = min(alc, blc)
    for i in range(l):
        x = aident[i]; y = bident[i]
        if x == y:
            continue
        nx = isinstance(x, (int, type(None))); ny = isinstance(y, (int, type(None)))
        if nx != ny:
            return 1 if nx else -1                 # numeric < non-numeric
        if isinstance(x, int) and isinstance(y, int):
            return 1 if x > y else -1
        elif isinstance(x, str) and isinstance(y, str):
            d = (x > y) - (x < y)
            return d if d != 0 else None
    # Shared prefix: longer wins for numeric prefixes only (build metadata is not a prerelease),
    # otherwise equal. The length comparison of the full identifiers matches the above logic.
    if alc == blc or not all(isinstance(x, int) for x in aident + bident):
        return 0
    else:
        return -1
