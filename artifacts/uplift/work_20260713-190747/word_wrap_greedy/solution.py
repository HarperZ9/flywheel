def wrap_text(s, width):
    if not isinstance(width, int) or isinstance(width, bool) or width < 1:
        raise ValueError('bad width')

    words = s.split()
    result = []
    current_line = ''

    for word in words:
        if len(current_line) + len(word) + (1 if current_line else 0) <= width:
            current_line += (' ' if current_line else '') + word
        else:
            if current_line:
                # Handle long word(s)
                parts = [current_line[:width]]
                start = width
                while start < len(word):
                    parts.append(word[start:start + width])
                    start += width
                parts.append(word[start:])
                result.extend(parts)
                current_line = ''
            else:
                if len(word) > width:
                    parts = [word[i:i + width] for i in range(0, len(word), width)]
                    result.extend(parts)
                else:
                    result.append(word)

    if current_line:
        # Handle trailing words
        parts = [current_line[:width]]
        start = width
        while start < len(current_line):
            parts.append(current_line[start:start + width])
            start += width
        result.extend(parts)

    return [line.strip() for line in result if line.strip()]
