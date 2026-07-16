import itertools

def count_covered(intervals):
    if any(not isinstance(b, int) or isinstance(b, bool) for interval in intervals for b in interval):
        raise ValueError('bad interval')
    if any(s > e for s, e in intervals):
        raise ValueError('bad interval')
    points = set(itertools.chain.from_iterable(range(s, e + 1) for s, e in intervals))
    return len(points)
