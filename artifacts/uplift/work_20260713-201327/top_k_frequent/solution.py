import collections

def top_k(items, k):
    """
    Return the k most frequent strings in a list, as a list of the strings themselves,
    without frequencies.
    
    Args:
    items: A list of strings.
    k: An integer specifying how many frequent strings to return.
    Returns:
    A list of unique strings that are among the top k frequent strings (not their frequencies).
    """
    if not 0 <= k < len(items):
        raise ValueError('bad k')
    
    item_count = collections.Counter([item for item in items])
    sorted_items_by_frequency = sorted(item_count.items(), key=lambda x: (-x[1], x[0]))
    top_k_strings = [string for _, string in sorted_items_by_frequency[:k]]
    return top_k_strings

# Check function to verify the correctness of the solution
def check_solution():
    assert isinstance(top_k(["i", "love", "leetcode"], 2), type(None)
    assert len(top_k(["the", "day", "is", "sunny", "the", "plant", "are"] ,4)) == 3, 'The top 4 are not in the right order'
    assert sorted(top_k(["i", "love", "leetcode"], 2)) == ["i", "love"]
    print("All tests passed!")

# Run the check function to verify the solution
check_solution()
