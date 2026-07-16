def eval_bool(expr):
    if not isinstance(expr, str):
        raise ValueError('bad expr')
    
    expr = expr.replace(" ", "")
    allowed_chars = set("TF&|!()")
    if not all(c in allowed_chars for c in expr):
        raise ValueError('bad expr')
    
    try:
        def parse(expr):
            stack = []
            current = ""
            i = 0
            while i < len(expr):
                if expr[i] == '(':
                    stack.append(current)
                    current = ""
                elif expr[i] == ')':
                    if not stack:
                        raise ValueError('bad expr')
                    previous = stack.pop()
                    current = previous + current
                else:
                    current += expr[i]
                i += 1
            
            return current
        
        expr = parse(expr)
        
        def eval_expr(expr):
            stack = []
            operators = {"&": lambda x, y: x and y, "|": lambda x, y: x or y, "!": lambda x: not x}
            
            for token in expr:
                if token.isdigit():
                    val = True if int(token) else False
                    stack.append(val)
                elif token in operators:
                    args = [stack.pop() for _ in range(2)]
                    result = operators[token](*args)
                    stack.append(result)
            
            return stack[0]
        
        return eval_expr(expr)
    
    except Exception as e:
        raise ValueError('bad expr')
