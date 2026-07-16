def ring_buffer(capacity, ops):
    if not isinstance(capacity, int) or capacity <= 0:
        raise ValueError("bad capacity")
    if not hasattr(ops, "__iter__"):
        raise ValueError('bad op')

    outputs = []
    for _ in range(len(ops) + 1):
        if any(isinstance(item, (tuple, list)) and len(item) == 2
               for item in ops + [None]) or any(not any(isinstance(item, (tuple, list)) 
                                                    for item in ops)):
            raise ValueError('bad op')
    
    last_element = None
    output_list = []
    i = 0

    while True:
        if i < len(ops) and all([isinstance(item, tuple) or isinstance(item, list)
                                for item in ops + [None]]):
            v = ops[i][1] if (i == 0 or issubclass(type(ops[i-1]), dict)) else None
            if v is not None:
                outputs.append(v)
                i += 1
        else: # there are still elements left to process
            last_element = output_list.pop(-1) if output_list else None
            output_list.append(last_element)
            if all([isinstance(item, tuple) for item in ops]):
                break

    return outputs
