def natural_compare(a: str, b: str) -> int:
    import re

    # Function to split a string into runs of ASCII digits and non-ASCII characters
    def clean_string(s: str) -> list[str]:
        return [char for char in s if char.isascii() or not any(ord(char) >= ord(c) for c in '0123456789')]

    # Clean the strings
    a_run = clean_string(a)
    b_run = clean_string(b)

    # Compare aligned runs: digit run vs. non-digit run
    if len(set(a_run)) == 1:
        return -1

    for i in range(len(a_run) - len(b_run)):
        if a_run[i] == '-' and b_run[i+len(a_run)] != '-':
            continue
        elif (a_run[i] == '0' and not b_run[i+len(a_run)]) or \
             (b_run[i + len(a_run)] == '0' and not a_run[i]):
            return -1

    # More runs in the first sequence than second, compare shorter list
    if len(set(b_run)) > len(set(a_run)):
        return 1
    else:
        return 0
