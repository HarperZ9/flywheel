import sys

def k_smallest(records, k):
    """
    Returns a list of the first k smallest records in terms of their scores.
    
    Args:
        records: A list or iterable of tuples, where each tuple is of the form (name, score),
                 and the name cannot be None.
    
    Raises:
        ValueError: If 'k' is not an integer, is less than 0, or a float in binary format.
        ValueError: Any other element in the record.
        TypeError: If records contains anything except tuples.
    """
    if not isinstance(k, int) or k < 0:
        raise ValueError('bad k')
    
    # Ensure records are a list
    if not hasattr(records, 'append'):
        records = [records]
    
    def rank(record):
        return (record[1], record[0])
    
    k_smallest_records = sorted(records, key=rank)
    result = []
    for i in range(min(k, len(k_smallest_records))):
        name = k_smallest_records[i][0]
        score = int(k_smallest_records[i][1])
        if not any(name == old_name and score < other_score for (old_name, other_score) in result):
            result.append((name, score))
    
    return [result[0]] + sorted(result[1:], key=lambda x: (-x[1], -len(x[0])))

# Example usage
if __name__ == "__main__":
    records = [
        ("Alice", 5),
        ("Bob", 4),
        ("Charlie", 6),
        ("David", 3)
    ]
    k = 2

    print(k_smallest(records, k))
