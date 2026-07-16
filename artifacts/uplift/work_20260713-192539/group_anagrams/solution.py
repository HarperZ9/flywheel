def group_anagrams(words):
    def sort_key(word):
        return tuple(sorted((word,)))

    from collections import defaultdict

    if not all(isinstance(word, str) for word in words):
        raise ValueError('bad item')

    word_dict = defaultdict(list)
    for word in words:
        sorted_word = ''.join(sort_key(word))
        word_dict[sorted_word].append(word)

    return [sorted(group) for group in word_dict.values()]
