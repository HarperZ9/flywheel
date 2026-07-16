def wrap_text(s, width):
    if not isinstance(width, int) or width < 1:
        raise ValueError('bad width')
    
    words = s.split()
    lines = []
    current_line = []

    for word in words:
        if len(word) > width:
            # If the word is longer than the line's remaining space, start a new line
            while word:
                chunk, word = word[:width], word[width:]
                current_line.append(chunk)
                lines.append(' '.join(current_line))
                current_line = []
                if not word:
                    break
        else:
            # Append words to the current line until no more can fit on it
            remaining_space = width - len(' '.join(current_line) + ' ') if current_line else width
            while word and remaining_space >= 1:
                remaining_space -= len(word) + 1
                word = f"{word} " if not current_line else f" {word}"
                current_line.append(word)
    
    # Handle the last line, which may be incomplete
    lines[-1] = ' '.join(current_line)

    return lines
