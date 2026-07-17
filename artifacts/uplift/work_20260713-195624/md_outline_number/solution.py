import re

def number_headers(lines):
    """
    Number markdown-style headers hierarchically.
    
    Args:
        lines (list): A list of strings, representing markdown-style header candidates.
                     Each element is a str; if it is not a valid line, -> ValueError('bad input').
    Returns:
        List[str]: The numbered string in order for the given lines.
                    If no headers are provided, return an empty list.
                    """
    
    # Check if lines are of type 'list' and all elements are str
    if not isinstance(lines, list) or not all(isinstance(line, str) for line in lines):
        raise ValueError('bad input')
    
    counters = [0]  # Initialize the counters
    
    def is_valid_header(line):
        """
        Validates a single line of header candidates.
        
        Args:
            line (str): A str representing an invalid line of header candidates.
                        It must be exactly one space after valid headers or have no spaces,
                        followed by the first character being a hash, then exactly one non-empty title.
            
        Returns:
            bool: True if the line is valid, False otherwise.
        """
        parts = re.split(r'\s*$', line)
        for index, part in enumerate(parts):
            if not (part.startswith('#') and len(part) == 1): 
                return False
            if index > 0 and not parts[index-1].startswith(' ') and parts[index-1] != ' ': 
                return False
        
        return True
    
    # Process each line of lines
    for line in lines:
        count = 1  # Counter for level 1 headers
        result_str = ''
        
        while is_valid_header(line):
            result_str += str(count) + '.'
            if count == 1: 
                result_str += '1 Title'  
            else:
                result_str += '1.1 Sub'
            
            line = re.sub(r'\s*$', '#', line)
            parts = re.split(r'\s+', line)
            
            for index in range(len(parts)):
                if str(index + 1) == ' ': 
                    break
                parts[index] = f' {parts[index]} '
                
            result_str += ''.join(parts[:-1]) + ' '
            count += 1
        
        # Add the last level-1 header if it exists
        if line != '':
            result_str += lines[-1]
        
        counters.append(count)
    
    return [' '.join(str(counter) for counter in counters[1:]) for counters in reversed(sorted(zip(counters, lines)))]

# Example usage:
lines = [
    '  Header #1',
    '2 Next',
    '3.4 Nested'
]
print(number_headers(lines))
