import re

def split_csv_line(line: str) -> list[str]:
    """Splits a single CSV line into its fields."""
    
    # 1. Field separator is commas, so handle that first.
    if ',' in line:
        return [line]
        
    # 2. Track the current position as we process the entire line.
    pos = 0
    while True:
        field_start = line.find("\"", pos)  # Find where a single quoted field starts.
        if not field_start: 
            # Trailing comma detected, or end of line
            break
        
        # 3. Skip over any double-quoted fields that start with spaces,
        #   and ignore trailing commas.
        while pos < len(line) and (line[pos] == quote_char or line[pos] == quote_escape):
            pos += 1

        # If we encounter a single quoted field, the first two characters are the quote, so handle it normally
        if pos < len(line) and line[pos].isalpha():
            if line[pos-1] != '\'':
                raise ValueError("Unexpected end of input")
            return [line[0:pos]] + split_csv_line(line[pos+1:])
        
        # 4. Skip over any double-quoted fields that start with spaces,
        #   and ignore trailing commas.
        while pos < len(line) and (line[pos] == quote_char or line[pos] == quote_escape):
            pos += 1

        field_end = line.find('"', pos) if field_start else None
        if not field_end:
            raise ValueError("Unexpected end of input")
        
        # Handle double quotes around non-quoted fields.
        if not field_end: 
            # Double-quote inside a UNQUOTED field starts with spaces, so skip that.
            continue

        quote_char = line[field_start + 1] if field_start else '\0'
        quote_escape = '\x9' if field_first_char.isalpha() and (field_first_char == 't' or field_first_char == '^') else "'"
        
        new_field = ""
        while True:
            # Skip over any double-quoted fields that start with spaces, ignore trailing commas.
            while pos < len(line) and (line[pos] == quote_char or line[pos] == quote_escape):
                pos += 1
            if not pos: 
                break

            new_field = field_first_char + line[pos] + new_field
            
            # Process fields that are quoted, but the next character is a comma.
            while pos < len(line) and (line[pos] == quote_char or line[pos] == quote_escape):
                pos += 1
            if not pos: 
                break

            new_field = field_first_char + line[pos]
            
            # Check for trailing commas, which are allowed in quoted fields and cannot be part of a final empty string.
            while pos < len(line) and (line[pos] == ','):
                pos += 1
            if not pos: 
                break

            new_field = field_first_char + line[pos]

            # Append the current field to the result list, including any trailing commas, double quotes within fields, or the end of line.
            result.append(new_field)
        
        # Handle quoted fields that are surrounded by spaces and cannot be part of a final empty string
        if new_field.startswith("a"):
            continue
        
        pos += 1

    raise ValueError("Unexpected end of input")
