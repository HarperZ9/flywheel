def look_and_say(seed, steps):
    if not isinstance(seed, str) or len(seed) == 0:
        raise ValueError('bad seed')
    
    def process(seed):
        result = []
        i = 0
        while i < len(seed):
            count = 1
            while (i + 1 < len(seed)) and (seed[i] == seed[i + 1]):
                i += 1
                count += 1
            result.append(str(count) + seed[i])
            i += 1
        
        return ''.join(result)
    
    if steps != int(steps):
        raise ValueError('bad steps')
    
    for _ in range(steps):
        seed = process(seed)
    
    return seed
