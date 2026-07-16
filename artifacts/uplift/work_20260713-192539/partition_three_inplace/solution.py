def partition_three(items, pivot):
    if not all(isinstance(x, int) for x in items + [pivot]):
        raise ValueError("All elements must be integers")

    less_than_pivot, equal_to_pivot, greater_than_pivot = [], [], []
    
    for item in items:
        if item < pivot:
            less_than_pivot.append(item)
        elif item == pivot:
            equal_to_pivot.append(item)
        else:  # item > pivot
            greater_than_pivot.append(item)

    items[:] = (less_than_pivot + equal_to_pivot + greater_than_pivot)
    
    return items
