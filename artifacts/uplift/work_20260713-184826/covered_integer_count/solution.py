def count_covered(intervals):
    if not intervals:
        return 0

    # Create a set to store covered integers
    covered = set()

    for start, end in intervals:
        if not isinstance(start, int) or not isinstance(end, int):
            raise ValueError('bad interval')
        if start > end:
            raise ValueError('bad interval')

        # Add all integers from start to end (inclusive) to the set
        for i in range(start, end + 1):
            covered.add(i)

    return len(covered)
