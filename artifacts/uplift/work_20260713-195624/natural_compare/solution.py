def natural_compare(a: str, b: str) -> int:
    from collections import deque

    def compare_run(s1, s2):
        runs, i = deque(), 0
        while i < len(s1) or i < len(s2):
            if not s1[i].isdigit():
                if i == len(s1) - 1 and (s1[i+1] in '0'):  # non-digit at end of first string
                    return -1
                runs.append(s2)
            elif not s2[i].isdigit():
                runs.append(s1)
            else:
                s1, s2 = s2, s1  # move to next run for the same index
                i += 1
        if len(runs):
            return runs[0] - runs[-1]
        return 0

    # Compare using natural order and deque to handle large input sizes efficiently
    result = compare_run(deque(a), deque(b))
    return -result if result != 0 else 1 if len(result) == len(min(a, b)) else 0
