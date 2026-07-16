def wrap_text(s: str, width: int) -> list:
    if not isinstance(width, int) or width < 1:
        raise ValueError('bad width')
    
    words = s.split()
    lines = []
    current_line = []
    
    for word in words:
        if len(" ".join(current_line + [word])) > width:
            # If the current line plus the next word exceeds the width, split it
            while len(" ".join(current_line)) > 0 and len(" ".join(current_line)) + len(word) > width:
                lines.append(" ".join(current_line))
                if len(word) < width:
                    break
                remaining = word[:width]
                word = word[width:]
                current_line[-1] += remaining
            else:
                last_word = True
        # If the current line plus the next word is within or below the limit, add it to the current line
        if len(" ".join(current_line)) + len(word) <= width and not last_word:
            current_line.append(word)
        elif not last_word:
            lines.append(" ".join(current_line))
            current_line = [word]
    else:  # This is the same as 'else: break' with a for loop
        if current_line:
            lines.append(" ".join(current_line))
    
    return lines
