def glob_match(pattern: str, name: str) -> bool:
    if not isinstance(pattern, str) or not isinstance(name, str):
        raise ValueError('bad input')
    if not pattern:
        return not name
    first = pattern[0]
    if first == '*':
        if len(pattern) == 1:
            return True
        for i in range(len(name) + 1):
            if glob_match(pattern[1:], name[i:]):
                return True
        return False
    elif first == '?':
        if not name:
            return False
        return glob_match(pattern[1:], name[1:])
    else:
        if not name or name[0] != first:
            return False
        return glob_match(pattern[1:], name[1:])


# (the provided check; run it yourself, do not add to the function above)
from pathlib import Path

root = Path('/tmp/glob-check-3e6h8d')
root.mkdir(parents=True, exist_ok=True)
for leaf in ('a.txt', 'aa.txt', '?x?.txt'):
    (root / leaf).write_text('')

checked = []
for p in root.iterdir():
    checked.append((p.stem, glob_match('a*.txt', p.name)))

assert set(checked) == {('a.txt', True), ('aa.txt', True)}, checked
