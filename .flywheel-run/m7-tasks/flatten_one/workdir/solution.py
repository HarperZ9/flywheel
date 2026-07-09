def flatten_one(items):
    flattened_list = []
    for item in items:
        if isinstance(item, list):  # Check if the item is a list
            flattened_list.extend(item)  # Extend the result with the elements of the list
        else:
            flattened_list.append(item)  # Append non-list items directly to the result
    return flattened_list

# Example usage:
example_list = [1, [2, 3], 4, [5, 6], 7]
print(flatten_one(example_list))  # Output: [1, 2, 3, 4, 5, 6, 7]
