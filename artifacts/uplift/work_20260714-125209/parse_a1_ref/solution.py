def parse_a1(ref):
    if not isinstance(ref, str) or not ref:
        raise ValueError('bad ref')
    letters = ''
    i = 0
    while i < len(ref) and 'A' <= ref[i] <= 'Z':
        letters += ref[i]
        i += 1
    if not letters or i >= len(ref):
        raise ValueError('bad ref')
    row_part = ref[i:]
    if not (row_part[0] in '123456789' and all(c in '0123456789' for c in row_part)):
        raise ValueError('bad ref')
    col = sum((ord(letters[j]) - ord('A') + 1) * (26 ** (len(letters) - j - 1)) for j in range(len(letters)))
    row = int(row_part)
    if row <= 0:
        raise ValueError('bad ref')
    return (row, col)
