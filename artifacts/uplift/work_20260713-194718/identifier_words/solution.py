def split_identifier(s: str) -> list:
    if not s or all(c == '_' for c in s):
        return []
    
    def next_word():
        nonlocal index, words

        # Remove leading underscores
        while index < len(s) and s[index] == '_':
            index += 1
        
        # Find the start of the word
        if index >= len(s) or not s[index].isalnum():
            return 
        
        run = ''
        
        # Process runs of letters, digits, or consecutive _ until a different case letter is found
        for i in range(index, min(len(s), index + 30)):  # Arbitrary upper limit to prevent infinite loops with very long identifiers
            if s[i].isalnum() or s[i] == '_':
                run += s[i]
            else:
                break
        
        # If a digit/letter was found, start of word is the last letter/digit before _ or invalid char
        index = len(run) - 1 if any(c.isdigit() or c.isalpha() for c in reversed(run)) else -1

        # Handle acronyms and capitalizations
        while index >= 0:
            if s[index].islower():
                break
            elif s[index] == '_' and run[-1:].isdigit():
                words.append(run[-1:])
                return 
            elif s[index].isupper() and (index + 1 < len(s) and s[index + 1].islower()):
                words.append(s[index:index + 2])
                index += 1
            else:
                if run[0:1].isdigit():
                    words.append(run[:len(run)])
                    break
                elif not run[0:1].isalpha() or all(c.istitle() for c in run):
                    words.append(''.join(reversed(run)))
                    break
                index -= 1
        
        # Handle runs of letters and digits, remove leading underscores
        valid_run = ''.join(filter(str.isalnum, run))
        
        if len(valid_run) and not (any(c.isdigit() for c in run) or all(c.islower() for c in run)):
            words.append(''.join(filter(str.isalnum, run)))
            
        # Handle runs of consecutive underscores
        while index > -1 and s[index] == '_':
            index -= 1
        
        if index >= 0:
            valid_run = s[index:index + len(run)]
            for i in range(len(valid_run)):
                if not valid_run[i].isalnum() or (i < len(valid_run) - 1 and valid_run[i:i+2] == '__'):
                    break
                words.append(''.join(filter(str.isalnum, valid_run[:i])))
            
        # Handle trailing underscores
        while index > -1 and s[index] == '_':
            index -= 1
        
        if index >= 0:
            valid_run = ''.join(filter(str.isalnum, s[index:len(run)]))
            for i in range(len(valid_run)):
                if not valid_run[i].isalnum() or (i < len(valid_run) - 1 and valid_run[i:i+2] == '__'):
                    break
                words.append(''.join(filter(str.isalnum, valid_run[:i])))
        
        # Increment index after processing run
        index += len(run)
    
    if not s: 
        return []
    
    index = 0
    words = []
    next_word()
    
    while index < len(s):
        next_word()
    
    return words
