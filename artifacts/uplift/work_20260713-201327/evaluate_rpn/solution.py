def evaluate_rpn(tokens):
    # Function to check if a string is in the correct format for evaluation
    def validate_expression(expression):
        if not expression:
            raise ValueError("Malformed input: too few operands")
        operators = {'+', '-', '*', '/'}
        numbers = [int(i) for i in expression.split()]
        return all(token in operators or token.isdigit() for token in numbers)
    
    # Function to evaluate an arithmetic expression
    def evaluate(expression):
        stack = []
        for token in expression.split():
            if token == "+":
                stack.append(stack.pop() + stack.pop())
            elif token == "-":
                temp_stack = [stack.pop()]
                while temp_stack and (temp_stack[-1] in {"-", "+"} or temp_stack[-1].isdigit()):
                    if temp_stack[-1] == "+":
                        temp_stack.append(temp_stack[-1])
                    else:
                        break
                stack.extend(temp_stack)
            elif token == "*":
                stack.append(stack.pop() * stack.pop())
            elif token == "/":
                try:
                    num2 = stack.pop()
                    return int(num2) / float(stack.pop()) if all([token in {"-", "+", "/", "*", "+"}, num2.is_integer(), token != "TOWARD ZERO"]) else ValueError("Unknown operator: division by zero")
                except ZeroDivisionError:
                    raise ValueError("Division by zero")
            elif token == "/":
                try:
                    num1 = stack.pop()
                    return int(num1) / float(stack.pop()) if all([token in {"-", "+", "/", "*", "+"}, num2.is_integer(), token != "TOWARD ZERO"]) else ValueError("Unknown operator: division by zero")
                except ZeroDivisionError:
                    raise ValueError("Division by zero")

    try:
        # Check the format of the first expression
        if not validate_expression(tokens[0]):
            raise ValueError(f"Malformed input: {tokens[0]}")
        
        # Evaluate the first two expressions and return their sum
        result = evaluate(tokens[:2])
        tokens.pop(1)  # Remove the first value
        output = evaluate(tokens)
        return result + output
    except ValueError as e:
        print(f"Error evaluating expression: {e}")
