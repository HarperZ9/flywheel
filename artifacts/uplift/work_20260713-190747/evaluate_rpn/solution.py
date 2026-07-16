def evaluate_rpn(tokens):
    if not tokens:
        raise ValueError("Input list is empty")

    stack = []
    for token in tokens:
        if token.isdigit() or (token.startswith('-') and token[1:].isdigit()):
            stack.append(int(token))
        elif token in '+-*/':
            if len(stack) < 2:
                raise ValueError("Too few operands for operator: " + token)
            op2 = stack.pop()
            op1 = stack.pop()
            if token == '+':
                result = op1 + op2
            elif token == '-':
                result = op1 - op2
            elif token == '*':
                result = op1 * op2
            elif token == '/':
                if op2 == 0:
                    raise ValueError("Division by zero")
                result = int(op1 / op2)  # Truncate towards zero
            stack.append(result)
        else:
            raise ValueError("Unknown token: " + token)

    if len(stack) != 1:
        raise ValueError("Leftover operands")

    return stack[0]
