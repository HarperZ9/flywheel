def min_stack(ops):
    if not isinstance(ops, list):
        raise ValueError('bad ops')
    
    stack = []
    output = []
    
    for op in ops:
        match op:
            case ('push', v) if isinstance(v, int): 
                stack.append(v)
                output.append(None)
            case ('pop'):
                if not stack:
                    raise ValueError('empty stack')
                else:
                    val = stack.pop()
                    output.append(val)
            case ('top'):
                if not stack:
                    raise ValueError('empty stack')
                else:
                    output.append(stack[-1])
            case ('min'):
                if not stack:
                    raise ValueError('empty stack')
                else:
                    min_val = float('inf')
                    for val in stack:
                        if val <= min_val:
                            min_val = val
                    output.append(min_val)
            case _:
                raise ValueError('bad op')
    
    return output
