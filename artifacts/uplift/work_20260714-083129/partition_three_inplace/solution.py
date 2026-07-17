def partition_three(items: list, pivot: int) -> list:
    if not all(isinstance(i, (int, bool)) and isinstance(pivot, (int, bool)) for i in items):
        raise ValueError("All elements must be integers or bool subclasses.")

    n = len(items)
    left, middle, right = 0, 0, n-1

    while middle <= right:
        if items[middle] < pivot:
            items[left], items[middle] = items[middle], items[left]
            left += 1
            middle += 1
        elif items[middle] == pivot:
            middle += 1
        else:  # items[middle] > pivot
            items[right], items[middle] = items[middle], items[right]
            right -= 1

    return items
