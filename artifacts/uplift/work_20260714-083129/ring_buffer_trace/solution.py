def ring_buffer(capacity, ops):
    if not isinstance(capacity, int) or capacity < 1:
        raise ValueError('bad capacity')
    
    buffer = []
    output = []

    for op in ops:
        if op[0] == 'write':
            value = op[1]
            if len(buffer) >= capacity:
                dropped_element = buffer.pop(0)
                buffer.append(dropped_element)
                output.append(dropped_element)
            else:
                buffer.append(value)
                output.append(None)
        
        elif op[0] in ['read', 'peek']:
            if not buffer:
                raise ValueError('buffer empty')
            
            element_to_process = buffer.pop(0) if op[0] == 'read' else None
            element_to_process is not None and output.append(element_to_process)

    return output
