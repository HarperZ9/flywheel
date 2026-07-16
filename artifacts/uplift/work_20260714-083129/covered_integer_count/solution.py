def count_covered(intervals):
    if not intervals:
        return 0

    # Define a set to keep track of covered integers.
    covered = set()

    for start, end in intervals:
        # Ensure every interval satisfies start <= end.
        if start > end:
            raise ValueError('bad interval')

        # Add all integers from 'start' to 'end' (inclusive) to the set.
        covered.update(range(start, end + 1))

    return len(covered)
