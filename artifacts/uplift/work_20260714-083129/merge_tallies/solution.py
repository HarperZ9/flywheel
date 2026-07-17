def merge_tallies(a: dict, b: dict) -> dict:
    if not isinstance(a, dict) or not isinstance(b, dict):
        raise ValueError("Both inputs must be dictionaries.")
    
    for value in a.values() + b.values():
        if not isinstance(value, int):
            raise ValueError("All values in the input dictionaries must be integers.")

    result = {}
    # Combine counts
    for key in set(list(a.keys()) + list(b.keys())):
        count_a = a.get(key, 0)
        count_b = b.get(key, 0)
        merged_count = count_a + count_b
        if merged_count != 0:
            result[key] = merged_count
    
    # Return the new dict and not mutate 'a' or 'b'
    return {key: value for key, value in result.items()}
