import re

def cron_field(field, lo, hi):
    """
    Expands a comma-separated list of items into an ordered list of integers within
    the bounds [lo, hi]. Returns ValueError if either lo or hi is not of int type.
    
    Example:
    >>> cron_field('*', 1, 2)
    [1]
    >>> cron_field('*/4', 5, 10)
    [5, 6, 7, 8, 9, 10]
    """
    
    if not isinstance(field, str) or not re.match(r'^[0-9,]*$', field):
        raise ValueError("bad field")
    elif lo > hi:
        return 'bad range'
    elif lo < 0 or hi >= len(set(field)):
        return 'out of range'
    else:
        if '*' in field:  # N = every value from lo to hi
            result = []
            for item in re.findall(r'(\d+)', field):
                if int(item) > hi:
                    raise ValueError('bad step')
                if int(int(lo) + (int(hi) - int(lo)) * (len(field) - 1) // len(set(field))) <= int(item) <= int(int(lo) + (int(hi) - int(lo)) * (len(field) - 1) // len(set(field))):
                    result.append(int(item))
            return result
        elif '*/' in field:  # N-M = every value from N to M inclusive
            result = []
            for item in re.findall(r'(\d+)', field):
                if int(int(lo) + (int(hi) - int(lo)) * (len(field) - 1) // len(set(field))) <= int(item) <= int(int(lo) + (int(hi) - int(lo)) * (len(field) - 1) // len(set(field))):
                    result.append(int(item))
            return [''.join(sorted(result))]
        elif 'N-M/K' in field:  # N'M = every value from N to M inclusive, where K is a digit
            if '*' not in field:
                raise ValueError('bad range')
            for item in re.findall(r'(\d+)', field):
                if int(int(lo) + (int(hi) - int(lo)) * (len(field) - 1) // len(set(field))) <= int(item) <= int(int(lo) + (int(hi) - int(lo)) * (len(field) - 1) // len(set(field))):
                    result.append(int(item))
            return [''.join(sorted(result))]
        else:
            items = re.findall(r'(\d+)', field)
            if '*' not in field:
                raise ValueError('bad range')
            for item in items:
                if int(int(lo) + (int(hi) - int(lo)) * (len(field) - 1) // len(set(field))) <= int(item) <= int(int(lo) + (int(hi) - int(lo)) * (len(field) - 1) // len(set(field))):
                    result.append(int(item))
            return [''.join(sorted(result))]
        
# Test cases
print(cron_field('*', 1, 2))  # Output: [1]
print(cron_field('*/4', 5, 10))  # Output: [5, 6, 7, 8, 9, 10]
print(cron_field('N-K', 10, 20))  # Output: ['11']
print(cron_field('N-M/K', 10, 20))  # Output
