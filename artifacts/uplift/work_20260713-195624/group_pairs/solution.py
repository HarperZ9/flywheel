def group_pairs(pairs):
    """
    Groups key-value pairs into a dictionary such that each key maps to a list of its values,
    and duplicates (key, value) pairs are kept and not replaced.
    
    :param pairs: A list of tuples where every element is an exact 2-tuple. List may contain repeated elements.
    :return: A new dict with keys in order of their first occurrence and values ordered by keys' occurrences.
    """
    output = {}
    for key, value in pairs:
        if type(value) == tuple or (type(value) is list and len(value) != 2):
            raise ValueError("Invalid input. Each element must be exactly a 2-tuple.")
        
        # Avoid mutating the original list
        values = [value for _ in range(len(pairs))]
        output[key] = values
    return output
