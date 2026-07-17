def group_anagrams(words):
    if not all(isinstance(word, str) for word in words):
        raise ValueError('bad item')
    
    anagram_groups = {}
    
    for word in sorted(words):  # Sort words to ensure groups are ordered by their first word
        key = tuple(sorted(word))
        if key in anagram_groups:
            anagram_groups[key].append(word)
        else:
            anagram_groups[key] = [word]
    
    return list(anagram_groups.values())
