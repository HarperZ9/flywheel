def min_stack(ops):
    if not isinstance(ops, list):
        raise ValueError('bad ops')
    
    stack = []
    outputs = []
    
    for op in ops:
        if len(op) != 2 or op[0] not in ('push', 'pop', 'top', 'min'):
            raise ValueError('bad op')
        
        cmd, value = op
        
        if cmd == 'push':
            stack.append(value)
            outputs.append(('push', value))
        elif cmd == 'pop':
            if not stack:
                raise ValueError('empty stack')
            else:
                outputs.append(('pop', None))
                stack.pop()
        elif cmd == 'top':
            if not stack:
                raise ValueError('empty stack')
            else:
                outputs.append(('top', stack[-1]))
        elif cmd == 'min':
            if not stack:
                raise ValueError('empty stack')
            else:
                min_value = min(stack)
                outputs.append(('min', min_value))
    
    return outputs
