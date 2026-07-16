def cron_field(field, lo, hi):
    if not (isinstance(lo, int) and isinstance(hi, int)):
        raise ValueError('bad bounds')
    
    if not (lo <= hi):
        raise ValueError('bad bounds')
    
    def parse_range_or_step(range_str):
        n, m, step = None, None, None
        parts = range_str.split('/')
        
        for part in parts:
            valid_parts.append(part)
            if len(part) == 0 or not part[0].isdigit() or \
               (len(part) > 1 and part[0] in '+-') or \
               (part.count('-') != 1 and '-' not in part):
                raise ValueError('bad field')
                
            n, m = int(part.split('-', maxsplit=2)[0]), int(part.split('-', maxsplit=2)[-1])
            if (n == 0 or m == 0) and len(valid_parts) > 1:
                raise ValueError('bad step')
            
            if '-' in part:
                if not n <= m:
                    raise ValueError('bad range')
                
                for i in range(n, m+1):
                    yield i
            else:
                if not (n and m):
                    raise ValueError('bad field')
                
                if int(part) < 0 or int(part) >= hi + 1:
                    raise ValueError('out of range')
                
                step = int(part)
                for i in range(n, hi + 1, step):
                    yield i
        
        return valid_parts

    # Split the cron-style field string
    items = field.split(',')

    valid_items = []
    
    for item_str in items:
        if not item_str or '-' in item_str and '/' not in item_str: 
            raise ValueError('bad field')
        
        try:
            valid_items.extend(parse_range_or_step(item_str))
        except ValueError as e:
            raise ValueError(f'bad field') from e

    yield from sorted(set(valid_items))

# Example usage
try:
    print(list(cron_field("@daily", 0, 60)))
except ValueError as e:
    print(e)
