from typing import List

def count_covered(intervals: List[List[int]]) -> int:
    covered = set()
    for interval in intervals:
        if len(interval) != 2 or not all(isinstance(b, int) and not isinstance(b, bool)
                                         for b in interval):
            raise ValueError('bad interval')
        start, end = interval
        if start > end:
            raise ValueError('bad interval')
        covered.update(range(start, end + 1))
    return len(covered)
