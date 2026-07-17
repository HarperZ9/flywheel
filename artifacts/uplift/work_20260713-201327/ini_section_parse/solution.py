import re

def parse_ini(text):
    """
    Parse a sectioned INI document into a dictionary.
    
    Parameters:
    text (str): A string with INI document structure, processed to remove empty lines and comments.
    
    Returns:
    dict: A dictionary mapping sections to their contents. If an attribute is missing,
          it will raise a KeyError. If the content of a section has invalid characters or
          its keys cannot be converted to integers/strings as attributes, it will raise a ValueError.
    """
    lines = text.strip().split('\n')
    ini_data = {}

    for line in lines:
        if not line:  # Skip empty lines and comments
            continue

        if line.startswith(';') or (line[0] == '[' and line[-1] == ']'):
            continue  # Skip section headers
        
        sections, attributes = _parse(line)
        ini_data[sections] = {k: v for k, v in zip(attributes, sections)}
    
    return ini_data

def _parse(s):
    """
    Helper function to parse an INI string into attributes and values.
    
    Parameters:
    s (str): An INI string with non-empty lines separated by spaces or newlines.
    
    Returns:
    tuple: A tuple containing the attribute names as a list, and their corresponding values
           as a dictionary.
    """
    sections = []
    attributes = {}
    while True:
        line = s.strip()
        
        if not line:
            break  # End of string

        if line.startswith('['):
            # Section header: strip spaces, tabs, and split by comma
            header = ' '.join(line[len('['):].split(','))
            sections.append(header)
            attributes[header] = []

        elif line.startswith(';'):
            # Comment: strip leading whitespace, add to the end of the list
            section_header, comment_text = line[len('['):], s.strip()]
            if not comment_text.lower().startswith('#'):
                raise ValueError(f'Bad section - {section_header}')
        
        # Regular expression patterns for key-value attribute mappings
        pattern = r'\w+=(\w+)'
        matches = re.findall(pattern, line)
        
        for header in sorted(matches):
            attributes[header] = [value.strip() for value in matches if value]
    
    return sections, attributes

# Example usage:
text = """
[foo]
bar: baz
[baz]
qux: quux
[some.section.key1]: some.value
[some.section.key2]: some.value
"""

ini_data = parse_ini(text)
print(ini_data)  # Output should be {section_name: {'key': value}}
