import math

def gray_rank(bits):
    if not isinstance(bits, str) or len(bits) == 0:
        raise ValueError('bad code')
    n = len(bits)
    for c in bits:
        if c not in ('0', '1'):
            raise ValueError('bad code')
    i = int(bits, 2)
    r = 0
    while i > 0:
        r ^= i
        i >>= 1
    return r

# Example usage:
print(gray_rank("000"))  # Output: 0
print(gray_rank("001"))  # Output: 1
print(gray_rank("011"))  # Output: 2
print(gray_rank("010"))  # Output: 3
print(gray_rank("110"))  # Output: 4
print(gray_rank("111"))  # Output: 5
print(gray_rank("101"))  # Output: 6
print(gray_rank("100"))  # Output: 7
