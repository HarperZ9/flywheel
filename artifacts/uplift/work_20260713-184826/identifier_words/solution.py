def split_identifier(s):
    if not s or s.replace('_', '').strip() == '':
        return []

    import re

    # Helper function to process acronyms and capitalized words
    def process_word(m):
        word = m.group(0)
        if any(c.islower() for c in word):
            return ' '.join(word[i-1:i+1] for i in range(1, len(word)) if word[i].isupper())
        else:
            return word

    # Regular expression to match allowed characters and splits
    pattern = re.compile(r'[_a-zA-Z0-9]+')

    # Find all matches and process them
    words = [process_word(m) for m in re.finditer(pattern, s)]

    return [w.strip() for w in ' '.join(words).split()]

# Example usage:
# print(split_identifier("This_is_a_test"))
# print(split_identifier("XMLHttpRequest"))
# print(split_identifier("__import__"))
