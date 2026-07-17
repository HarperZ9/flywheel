def wrap_text(s, width):
    """
    Greedy wrapping of text into lines.
    
    Parameters:
    s (str): The input string to be wrapped.
    width (int): The maximum allowed width for each line.

    Returns:
    list: A list of strings, where the first element is always an empty space and subsequent elements are lines.
    """
    # Check if width is at least 1
    if width < 1:
        raise ValueError('bad width')

    words = s.split()
    result_lines = []

    # Find the maximum length of each word and calculate the number of words
    max_length = 0
    for i, word in enumerate(words):
        max_length = max(max_length, len(word))
        if i == len(words) - 1:
            break

    # Calculate the total width used by the words plus any padding needed on the right side
    remaining_width = width - (max_length + int(len(s) % width > 0))

    for word in words:
        line = ' '.join([''] * ((max_length + width - len(word)) // width))
        if not remaining_width:  # No more characters to add, add a space
            result_lines.append(' ')
        else:
            # Add the length of this word to the current line and continue joining words
            result_lines.append(f'{word} {remaining_width}')
            max_length = len(word)
            remaining_width -= width

    if remaining_width:  # Need more space at the end, add a space as well
        result_lines.append(' ')

    return result_lines
