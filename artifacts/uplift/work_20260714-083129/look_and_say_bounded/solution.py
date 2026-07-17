def look_and_say(seed, steps):
    def expand_run(run):
        return f"{len(run)}{run[0]}"
    
    if not isinstance(seed, str) or len(seed) == 0:
        raise ValueError('bad seed')
        
    for _ in range(steps):
        new_string = ''
        i = 0
        while i < len(seed):
            count = 1
            while i + count < len(seed) and seed[i] == seed[i + count]:
                count += 1
            if count > 9:
                raise ValueError('run overflow')
            new_string += expand_run(seed[i:i+count])
            i += count
        
        seed = new_string
    
    return seed
