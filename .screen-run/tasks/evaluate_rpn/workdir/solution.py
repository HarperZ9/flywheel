def evaluate_rpn(tokens):
    st = []
    for t in tokens:
        if t in ('+', '-', '*', '/'):
            if len(st) < 2:
                raise ValueError('operands')
            b, a = st.pop(), st.pop()
            if t == '+':
                st.append(a + b)
            elif t == '-':
                st.append(a - b)
            elif t == '*':
                st.append(a * b)
            else:
                if b == 0:
                    raise ValueError('div0')
                st.append(int(a / b))
        else:
            try:
                st.append(int(t))
            except ValueError:
                raise ValueError(t)
    if len(st) != 1:
        raise ValueError('leftover')
    return st[0]
