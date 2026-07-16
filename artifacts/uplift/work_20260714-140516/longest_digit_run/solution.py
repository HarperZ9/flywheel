def longest_digit_run(n) -> tuple[int, int, int]:
    if not isinstance(n, int) or n < 0:
        raise ValueError('bad number')
    s = str(n)
    best_start, best_len = 0, 1
    run_start, run_len = 0, 1
    for i in range(1, len(s)):
        if s[i] == s[i - 1]:
            run_len += 1
        else:
            if run_len > best_len:
                best_start, best_len = run_start, run_len
            run_start, run_len = i, 1
    if run_len > best_len:
        best_start, best_len = run_start, run_len
    return best_start, best_len, int(s[best_start])
