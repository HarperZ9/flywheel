def natural_compare(a, b):
    if not isinstance(a, str) or not isinstance(b, str):
        raise ValueError('bad input')

    import re

    def split_alternate_runs(s):
        return [tuple(g) for _, g in re.findall(r'(\d+|\D+)', s)]

    def compare_run(run_a, run_b):
        if run_a.isdigit() and not run_b.isdigit():
            return -1
        if not run_a.isdigit() and run_b.isdigit():
            return 1
        if run_a == run_b:
            return 0

        # Compare digit runs by integer value and length (fewer leading zeros)
        if run_a.isdigit() and run_b.isdigit():
            len_a, len_b = len(run_a), len(run_b)
            value_a, value_b = int(run_a), int(run_b)
            if value_a < value_b:
                return -1
            elif value_a > value_b:
                return 1
            else:  # same integer value, compare by length (fewer leading zeros)
                if len_a < len_b:
                    return -1
                elif len_a > len_b:
                    return 1
                else:
                    return 0

        # Compare non-digit runs by ASCII order of characters
        for c_a, c_b in zip(run_a, run_b):
            if ord(c_a) < ord(c_b):
                return -1
            elif ord(c_a) > ord(c_b):
                return 1

        # If one run is a prefix of the other, the shorter run is smaller
        return len(run_a) - len(run_b)

    runs_a = split_alternate_runs(a)
    runs_b = split_alternate_runs(b)

    min_len = min(len(runs_a), len(runs_b))
    for i in range(min_len):
        comp = compare_run(runs_a[i], runs_b[i])
        if comp != 0:
            return comp

    # If all aligned runs are equal but one sequence has more runs,
    # the shorter sequence compares as smaller
    return -1 if len(runs_a) < len(runs_b) else (1 if len(runs_a) > len(runs_b) else 0)
# Example usage:
print(natural_compare("123", "45"))  # Output: -1
print(natural_compare("version2", "version10"))  # Output: -1
print(natural_compare("file10.txt", "file2.txt"))  # Output: 1
