import re

def parse_kv(s):
    if not isinstance(s, str):
        raise ValueError('bad input')
    items = [i.strip() for i in s.split(';') if i.strip()]
    seen = set()
    result = []
    for item in items:
        if '=' not in item:
            raise ValueError('bad item')
        parts = item.partition('=')
        key = parts[0].strip()
        value = parts[2]  # everything after the first =
        if not key or not re.fullmatch(r'[A-Za-z0-9_]+', key):
            raise ValueError('bad item')
        if key in seen:
            raise ValueError('duplicate key')
        seen.add(key)
        result.append((key, value))
    return result
