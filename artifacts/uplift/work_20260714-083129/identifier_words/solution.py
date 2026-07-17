def split_identifier(s):
    if not s:
        return []
    
    words = []
    in_word = False
    current_word = ""
    
    for i, char in enumerate(s):
        if char == "_" and (i == 0 or s[i-1] != "_"):
            continue
        if not in_word and char.isalnum():
            in_word = True
            current_word += char
        
        elif in_word:
            if char.isspace() and i < len(s)-1 and s[i+1].isupper():
                words.append(current_word)
                current_word = ""
                in_word = False
            elif char.isdigit() or (char.isalpha() and not current_word[0].isdigit()):
                if i == len(s) - 1 or current_word[-1].islower() and s[i+1].isdigit():
                    final_char = s[i+1] if i < len(s)-2 else ""
                    words.append(current_word + char)
                    in_word = False
                    continue
                
                if (current_word[0].isupper() and char.islower()) or (char.isdigit() == current_word[-1].isdigit()):
                    # Acronym logic
                    final_char = s[i+1] if i < len(s)-2 else ""
                    if final_char != "_" and final_char not in "_.1234567890":
                        words.append(current_word)
                        words.append(char + final_char)
                    elif final_char == "_":
                        words.append(current_word + char + "_")
                    current_word = ""
                else:
                    current_word += char
                
    if i < len(s)-1 and s[i+1] not in "._01234567890":
        words.append(current_word)
    
    return words
