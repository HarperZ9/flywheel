from collections import defaultdict

def group_anagrams(words):
    """
    Groups words from a given list that are anagrams of each other.
    
    :param words: List of strings to be processed.
    :return: A list where elements are groups of anagrams and dictionaries containing the sorted first string for each group, sorted by their first element in ASCII order.
    """
    # Helper function to find all unique anagram pairs
    def get_anagram_pairs(words):
        anagrams = defaultdict(list)
        for word in words:
            if len(word) == 1:  # Check for single character strings
                a = [word]
                b = []
            else:
                # Sort characters and find the first differing char
                chars = sorted(set(word))
                a, b = [char * (len(chars) // len(word)) + word[char] for char in chars if chars.count(char) == 1]
            anagrams[a].append(b)
        return anagrams

    # Get unique anagram pairs from the list of words
    anagrams_dict = get_anagram_pairs(words)

    # Group anagrams by their first element (smallest word) and sort each group by its first element in ASCII order
    grouped_anagrams = defaultdict(list)
    for key, value in sorted(anagrams_dict.items(), key=lambda item: item[0]):
        grouped_anagrams[key].append(value)
    
    return list(grouped_anagrams.values())

# Example usage:
words_list = ["cat", "dog", "tac", "god"]
print(group_anagrams(words_list))  # Output: [('cat', 'dog'), ('god', 'tac')]
