def group_anagrams(words):
    if not all(isinstance(word, str) for word in words):
        raise ValueError('bad item')

    def group_anagram_helper(group):
        sorted_group = sorted(group)
        seen = set()
        result = []
        for word in sorted_group:
            anagram_tuple = tuple(sorted(word))
            if anagram_tuple not in seen:
                result.append(anagram_tuple)
                seen.add(anagram_tuple)
        return [list(w) for w in result]

    groups = {}
    for word in words:
        key = (word, len(word))
        if key not in groups:
            groups[key] = []
        groups[key].append((word, len(word)))

    for group in groups.values():
        group.sort(key=lambda x: x[0])
        groups[key].sort()

    return [item[1] for item in sorted(groups.items(), key=lambda x: x[0])]
