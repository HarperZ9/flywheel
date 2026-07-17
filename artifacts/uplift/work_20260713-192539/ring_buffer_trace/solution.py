def ring_buffer(capacity, ops):
    if not isinstance(capacity, int) or capacity < 1:
        raise ValueError('bad capacity')
    
    buffer = []
    outputs = []

    for op in ops:
        if op == ('write', v := next(iter(v))) if isinstance(op, tuple) else (op[0], None if len(op) != 1 else next(iter(op))):
            if len(buffer) < capacity:
                buffer.append(v)
                outputs.append(None if v is None else v)
            else:
                buffer.pop(0)
                buffer.append(v)
                outputs.append(v)
        elif op == ('read',):
            if not buffer:
                raise ValueError('buffer empty')
            buffer.pop(0)
            outputs.append(buffer[0])
        elif op == ('peek',):
            if not buffer:
                raise ValueError('buffer empty')
            outputs.append(buffer[0])
        else:
            raise ValueError('bad op')

    return outputs
