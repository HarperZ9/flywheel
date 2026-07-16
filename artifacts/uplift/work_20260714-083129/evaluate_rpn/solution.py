def evaluate_rpn(tokens):
    if not tokens:
        raise ValueError("Input list cannot be empty.")
    
    stack = []
    operators = set(['+', '-', '*', '/'])
    
    for token in tokens:
        if token not in operators:
            # Token is an operand, push to the stack.
            try:
                stack.append(int(token))
            except ValueError as e:
                raise ValueError(f"Malformed input: {e}")
        else:
            # Token is an operator
            if len(stack) < 2:
                raise ValueError("Not enough operands.")
                
            right_operand = stack.pop()
            left_operand = stack.pop()

            try:
                if token == '+':
                    result = left_operand + right_operand
                elif token == '-':
                    result = left_operand - right_operand
                elif token == '*':
                    result = left_operand * right_operand
                elif token == '/':
                    # Division truncates TOWARD ZERO.
                    if right_operand < 0:
                        result = -(left_operand // abs(right_operand))
                    else:
                        result = left_operand // right_operand

            except ZeroDivisionError:
                raise ValueError("Division by zero.")
            
            stack.append(result)

    if len(stack) == 1:
        return stack[0]
    else:
        raise ValueError("Too many operands.")
