def evaluate_rpn(tokens):
    if len(tokens) < 3:
        raise ValueError("Too few operands")
    
    stack = []
    for token in tokens:
        if isinstance(token, str):  # Assuming all non-operand are operators
            op2, op1 = stack.pop(), stack.pop()
            
            if token == '+':
                stack.append(op1 + op2)
            elif token == '-':
                stack.append(op1 - op2)
            elif token == '*':
                stack.append(op1 * op2)
            elif token == '/':
                # Truncate towards zero
                if op1 < 0 and op2 < 0 or op1 > 0 and op2 > 0:
                    stack.append(op1 // op2)
                else:
                    stack.append(int(op1 / op2))
            else:
                raise ValueError(f"Unknown token {token}")
        else:
            stack.append(token)
    
    if len(stack) != 1:
        raise ValueError("Leftover operands")
    
    return stack[0]
