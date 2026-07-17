import re

def parse_kv(s):
    if not isinstance(s, str):
        raise ValueError("bad input")
    out = []
    seen = set()
    if s == "":
        return []
    for part in s.split(";"):
        m = re.match(r"^\s*([A-Za-z0-9_]+)\s*=\s*(.*)$", part)
        if not m:
            raise ValueError("bad item")
        key, value = m.groups()
        if key == "" or value.count("=") > 1 or key in seen:
            raise ValueError("bad item" if key == "" else "duplicate key")
        out.append((key, value))
        seen.add(key)
    return out
