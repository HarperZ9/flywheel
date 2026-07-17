def sliding_windows(items, size, step):
    if not isinstance(items, list):
        raise ValueError('bad input')
    
    if not isinstance(size, int) or size < 1:
        raise ValueError('bad size')
    
    if not isinstance(step, int) or step < 1:
        raise ValueError('bad step')

    windows = []
    for i in range(0, len(items) - size + 1, step):
        window = items[i:i+size]
        windows.append(window)
    
    return windows
