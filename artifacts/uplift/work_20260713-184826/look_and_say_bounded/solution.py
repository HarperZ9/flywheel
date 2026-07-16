def look_and_say(seed, steps):
    if not isinstance(seed, str) or len(seed) == 0 or not seed.isdigit():
        raise ValueError('bad seed')
    if not isinstance(steps, int) or bool(steps):  # Ensure steps is an int and not a bool
        raise ValueError('bad steps')

    def say(sequence):
        result = []
        i = 0
        while i < len(sequence):
            count = 1
            while i + 1 < len(sequence) and sequence[i] == sequence[i + 1]:
                i += 1
                count += 1
            if count > 9:
                raise ValueError('run overflow')
            result.append(str(count))
            result.append(sequence[i])
            i += 1
        return ''.join(result)

    for _ in range(steps):
        seed = say(seed)
    
    return seed
