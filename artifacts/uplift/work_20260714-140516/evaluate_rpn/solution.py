def evaluate_rpn(tokens):
    stack = []
    ops = {"+": lambda x, y: x + y, "-": lambda x, y: x - y,
           "*": lambda x, y: x * y, "/": lambda x, y: int(x / y)}
    for t in tokens:
        if t.isdigit() or (t.startswith("-") and t[1:].isdigit()):
            stack.append(int(t))
            continue
        if len(stack) < 2 or t not in ops: raise ValueError(f"{len(stack)}|{t}")
        a, b = stack.pop(), stack.pop()
        try: stack.append(ops[t](b, a))
        except ZeroDivisionError: raise ValueError("divide by zero")
    if len(stack) != 1: raise ValueError(len(stack))
    return stack[0]
