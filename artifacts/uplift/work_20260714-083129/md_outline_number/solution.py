def outline_number(lines):
    def is_valid_header(line, current_level):
        if len(line) > 7 or line[0] != "#":
            raise ValueError('bad header')
        level = line.count("#")
        if level > current_level + 1:
            return False
        
        # Ensure there's exactly one space after the hashes
        if not line.startswith(level * "#" + " "):
            return False
        
        title = line[level * "#" + " ".__len__():].strip()
        if title == "" or not title[0].isalnum() and not title[0] in ["-", "_"]:
            return False
        
        # Ensure no extra leading hashes
        for char in reversed(line[:level]):
            if char != "#":
                break
        else:
            return False
        
        return True
    
    def number_level(level, i):
        counter = [str(i) + "."]
        while counter and len(counter) <= level:
            yield "".join(counter)
            last = counter.pop()
            if last.endswith("."):
                last = last[:-1]
            counter.append(last + ".")
    
    def process_line(line, current_level=1):
        if line.strip().startswith("#"):
            for num in number_level(current_level, len(lines)):
                try:
                    return f"{num} {line[level * "#" :].strip()}"
                except IndexError:
                    pass
        
        raise ValueError('bad header')
    
    counter = [0]  # Counter for each level
    result = []
    
    for i, line in enumerate(lines):
        if not is_valid_header(line, max(counter)):
            continue
        number_line = process_line(line, counter.index(max(counter)) + 1)
        result.append(number_line)
        counter[counter.index(max(counter))] += 1
    
    return result
