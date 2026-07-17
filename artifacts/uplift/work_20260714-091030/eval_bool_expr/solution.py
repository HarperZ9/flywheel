def eval_bool(expr):
    def err(m): raise ValueError(f"bad expr")
    if not isinstance(expr, str) or not expr: err("bad expr")

    allowed = "TF(*)&|!"
    out = []
    paren = 0

    # check all chars valid and build output list (infix)
    for c in "".join(expr.split()):
        if c == " ":
            continue
        elif c in allowed:
            if c == "(": paren += 1
            elif c == ")": paren -= 1; if paren < 0: err("bad expr")
            out.append(c)
        else:
            err("bad expr")

    if paren != 0 or not out:
        err("bad expr")

    # shunting-yard (with left-associative NOT as prefix): ! binds tightest,
    # then & more tightly, then |; left associative within a precedence level
    ops = []
    vals = []
    i = 0

    while i < len(out):
        c = out[i]
        if c in "TF":
            try:
                v = {"T": True, "F": False}[c]
            except KeyError:
                err("bad expr")
            vals.append(v)
        elif c == "!":
            ops.append(c)
        elif c == "&" or c == "|":
            while ops and (ops[-1] == "&" or ops[-1] == "|"):
                if not vals: err("bad expr")
                rhs, lhs = vals.pop(), vals.pop()
                vals.append({"&": lambda a,b:a and b, "|": lambda a,b:a or b}[c](lhs, rhs))
            ops.append(c)
        elif c == "(":
            pass
        else:  # c == ")"
            while ops and ops[-1] != "(":
                if not (vals and len(vals) >= 2): err("bad expr")
                rhs, lhs = vals.pop(), vals.pop()
                op = ops.pop()
                f = {"&": lambda a, b: a and b, "|": lambda a, b: a or b}
                vals.append(f[op](lhs, rhs))
            if not ops or ops[-1] != "(":
                err("bad expr")
            ops.pop()  # discard (
        i += 1

    # remaining operators
    while ops:
        if len(vals) < 2: err("bad expr")
        rhs, lhs = vals.pop(), vals.pop()
        op = ops.pop()
        f = {"&": lambda a, b: a and b, "|": lambda a, b: a or b}
        vals.append(f[op](lhs, rhs))

    if len(vals) != 1:
        err("bad expr")

    return vals[0]
