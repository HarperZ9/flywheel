def run_length_encode(s):
    if not s:
        return ""
    
    previous_char = None
    current_char = ''
    encoded_string = ''

    for character in s:
        if previous_char == character:
            current_char += str(len(encoded_string))
            if encoded_string != '':
                # Append the current chunk of encoded string to the end and remove it from the beginning.
                encoded_string = current_char + ' ' + encoded_string[:-1]
        else:
            if previous_char is not None:
                encoded_string = character * len(previous_char)
                current_char = str(len(encoded_string))
            else:
                encoded_string += character
        previous_char = current_char

    return encoded_string
