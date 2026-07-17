def semver_compare(a: str, b: str) -> int:
    # Validate both are strings and parse
    for ver, name in [(a, 'a'), (b, 'b')]:
        if not isinstance(ver, str):
            raise ValueError(f'bad version')
        try:
            m = re.fullmatch(r'^(\d+)\.(\d+)\.(\d+)(?:-(.+))?', ver)
            if not m or m.group(1) == '0':
                raise ValueError()
        except (ValueError, AssertionError):
            raise ValueError(f'bad version')
    def identifiers(s): return tuple(int(p) if re.fullmatch(r'\d+', p) else p for p in s.split('.'))
    a_num = ((int(a.group(i)) for i in range(1, 4)), identifiers(getattr(a, 'group', lambda _: None)(4)))
    b_num = ((int(b.group(i)) for i in range(1, 4)), identifiers(getattr(b, 'group', lambda _: None)(4)))
    def cmp(t): return (t == (-1, -1)) - (t == (1, 1))
    for ai, bi in zip(a_num[0], b_num[0]):
        if ai != bi: return (-1, 1)[ai < bi]
    ln, rn = len(a_num[1]), len(b_num[1])
    if ln != rn and not all(a_num[1] or b_num[1]): return int(ln > rn) * 2 - 1
    for i in range(min(ln, rn)):
        ai, bi = a_num[1][i], b_num[1][i]
        isnum = lambda x: isinstance(x, int)
        if   isnum(ai) != isnum(bi): return int(isnum(bi)) * 2 - 1
        elif isnum(ai):             return (-1, 1)[ai < bi]
        else:                       return cmp((-1, 1)[ai < bi])
    return 0
