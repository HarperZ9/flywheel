def count_covered(intervals):
    if not intervals:
        return 0
    
    # Using a set to store unique integers covered
    covered = set()
    
    for start, end in intervals:
        for i in range(start, end + 1):
            covered.add(i)
            
    return len(covered)
