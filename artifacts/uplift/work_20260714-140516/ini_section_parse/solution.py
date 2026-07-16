def parse_ini(text):
    if not isinstance(text, str):
        raise ValueError("bad input")
    lines = text.splitlines()
    result = {}
    current_section = None
    seen_sections = set()

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith(";") or stripped.startswith("#"):
            continue
        if stripped[0] == "[":
            if not stripped.endswith("]"):
                raise ValueError("bad section")
            name = stripped[1:-1]
            if not name or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_" for c in name):
                raise ValueError("bad section")
            if name in seen_sections:
                raise ValueError("duplicate section")
            seen_sections.add(name)
            current_section = {}
            result[name] = current_section
        else:
            if "=" not in stripped:
                raise ValueError("bad line")
            pos = stripped.index("=")
            key = stripped[:pos].strip()
            value = stripped[pos + 1:].strip()
            if not key or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_" for c in key):
                raise ValueError("bad line")
            if current_section is None:
                raise ValueError("no section")
            if key in current_section:
                raise ValueError("duplicate key")
            current_section[key] = value

    return result
