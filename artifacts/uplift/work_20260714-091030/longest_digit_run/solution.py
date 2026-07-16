def longest_digit_run(n):
    if not isinstance(n, int) or n < 0:
        raise ValueError('bad number')
    s = str(n)
    best_start = best_len = 0
    i = 0
    while i < len(s):
        d = int(s[i])
        j = i + 1
        while j < len(s) and int(s[j]) == d:
            j += 1
        l = j - i
        if l > best_len or (l == best_len and i < best_start):
            best_start, best_len = i, l
        i = j
    return best_start, best_len, d
