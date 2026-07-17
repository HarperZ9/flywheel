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

        def fold(op):
            while j < len(t) and t[j] == op:
                j += 1
                if not vals or vals[-1] in "&|":
                    raise ValueError('bad expr')
                b = vals.pop()
                vals.append(not b)

        while j < len(t):
            x = t[j]
            j += 1
            if x == '(':
                v, j = parse(t, j)
                vals.append(v)
            elif x == ')':
                break
            elif x == '!':
                fold('!')
            elif x in "TF":
                vals.append(x == 'T')
            else:
                raise ValueError('bad expr')

        while j < len(t) and t[j] == '&':
            j += 1
            if not vals or vals[-1] in "|":
                raise ValueError('bad expr')
            b = vals.pop()
            r, _ = parse(t, j)
            vals.append(b and r)

        while j < len(t) and t[j] == '|':
            j += 1
            if not vals:
                raise ValueError('bad expr')
            vals.append(vals.pop() or parse(t, j)[0])

        return (
            True if vals else False,
            j
        )

    if not isinstance(expr, str):
        raise ValueError('bad expr')
    t = tokenize("".join(expr.split()))
    if not t:
        raise ValueError('bad expr')
    v, j = parse(t, 0)
    if j != len(t):
        raise ValueError('bad expr')
    return v
