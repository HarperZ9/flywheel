def eval_bool(expr):
    def tokenize(s):
        out = []
        i = 0
        while i < len(s):
            c = s[i]
            if c in "TFT&|!()":
                out.append(c)
                i += 1
            elif c.isspace():
                i += 1
            else:
                raise ValueError('bad expr')
        return out

    def parse(t, j):
        vals = []

        def eval_not():
            if t[j] != '!':
                return False
            while j < len(t) and t[j] == '!':
                j += 1
            v, _ = value()
            nonlocal vals
            vals[-1] = not v

        def value():
            tok = t[j]
            if tok == '(':
                j += 1
                rv, _ = parse(t, j)
                if t[j] != ')':
                    raise ValueError('bad expr')
                j += 1
                return rv, True
            elif tok == 'T':
                j += 1
                return True, False
            elif tok == 'F':
                j += 1
                return False, False
            eval_not()
            return vals[-1], True

        def term():
            v = None
            while j < len(t):
                if t[j] == '&' or (v is None and not value()[1]):
                    v = value()[0]
                    if v is None:
                        raise ValueError('bad expr')
                    eval_not()
                    vals.append(v)
                    v = None
                else:
                    break

        while j < len(t):
            term()
        if vals == []:
            return False, False
        return all(vals), True

    if not isinstance(expr, str):
        raise ValueError('bad expr')

    t = tokenize(expr)
    if not t:
        raise ValueError('bad expr')
    try:
        rv, consumed = parse(t, 0)
    except (IndexError, TypeError, ValueError):
        raise ValueError('bad expr') from None
    if not consumed or j < len(t) - 1:
        raise ValueError('bad expr')

    return rv
