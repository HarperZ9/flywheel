def min_stack(ops):
    if not isinstance(ops, list):
        raise ValueError('bad ops')
    
    output = []
    stack = []
    for op in ops:
        if len(op) != 1 or (op[0] != 'push' and op[0] != 'pop' and op[0] != 'top' and op[0] != 'min'):
            raise ValueError('bad op')
        
        if op == ('push',):
            if len(stack) > 0:
                stack.append(min(stack[-1], op[1]))
            else:
                stack.append(op[1])
            output.append(None)
        
        elif op == ('pop',):
            if not stack:
                raise ValueError('empty stack')
            output.append(stack.pop())
            
        elif op == ('top',):
            if not stack:
                raise ValueError('empty stack')
            output.append(stack[-1])
        
        elif op == ('min',):
            if not stack:
                raise ValueError('empty stack')
            output.append(stack[-1])
    
    return output
