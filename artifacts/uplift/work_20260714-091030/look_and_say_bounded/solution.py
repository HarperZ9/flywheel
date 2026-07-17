def look_and_say(seed, steps):
    if not isinstance(seed, str) or not seed:
        raise ValueError('bad seed')
    if any(c not in '0123456789' for c in seed):
        raise ValueError('bad seed')
    if not isinstance(steps, int) or isinstance(steps, bool):
        raise ValueError('bad steps')
    if steps < 0:
        raise ValueError('bad steps')
    if steps == 0:
        return seed
    current = seed
    for _ in range(steps):
        parts = []
        i = 0
        while i < len(current):
            j = i + 1
            while j < len(current) and current[j] == current[i]:
                j += 1
            run_length = str(j - i)
            if len(run_length) > 1:
                raise ValueError('run overflow')
            parts.append(run_length + current[i])
            i = j
        current = ''.join(parts)
    return current
