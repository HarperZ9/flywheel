def ring_buffer(capacity, ops):
    if not isinstance(capacity, int) or capacity < 1:
        raise ValueError('bad capacity')
    
    buffer = []
    output = []
    
    for op in ops:
        if len(op) != 2 and op not in (['read'], ['peek']):
            raise ValueError('bad op')
        
        if op == ('write',):
            v = None
        else:
            v = op[0]
            if buffer:
                output.append(buffer.pop(0))
        
        if v is not None:
            buffer.append(v)
            if len(buffer) > capacity:
                buffer.pop(0)
                output.append(v)
    
    return output
