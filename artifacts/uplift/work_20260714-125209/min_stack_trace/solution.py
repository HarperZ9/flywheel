def min_stack(ops):
    if not isinstance(ops, list):
        raise ValueError('bad ops')
    stack = []
    min_tracker = []
    out = []
    for op in ops:
        if len(op) != 2 and (op == ('pop',) or op == ('top',) or op == ('min',)):
            raise ValueError('bad op')
        kind = op[0]
        if kind == 'push':
            v = op[1]
            if not isinstance(v, int) or isinstance(v, bool):
                raise ValueError('bad op')
            stack.append(v)
            if min_tracker:
                min_tracker.append(min(min_tracker[-1], v))
            else:
                min_tracker.append(v)
        elif kind == 'pop':
            if not stack:
                raise ValueError('empty stack')
            out.append(stack.pop())
            min_tracker.pop()
        elif kind == 'top':
            if not stack:
                raise ValueError('empty stack')
            out.append(stack[-1])
        elif kind == 'min':
            if not min_tracker:
                raise ValueError('empty stack')
            out.append(min_tracker[-1])
    return out
