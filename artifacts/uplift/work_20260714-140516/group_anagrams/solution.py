def group_anagrams(words):
    if not isinstance(words, list):
        raise ValueError('bad item')
    from collections import defaultdict
    groups = defaultdict(list)
    for w in words:
        if not isinstance(w, str):
            raise ValueError('bad item')
        key = ''.join(sorted(w))
        groups[key].append(w)
    return sorted([sorted(v) for v in groups.values()])
