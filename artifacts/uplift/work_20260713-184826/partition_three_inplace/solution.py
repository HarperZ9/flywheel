def partition_three(items, pivot):
    if not all(isinstance(x, int) for x in items + [pivot]):
        raise ValueError("All elements must be integers")

    def swap(i, j):
        items[i], items[j] = items[j], items[i]

    left = 0
    right = len(items) - 1
    i = 0

    while i <= right:
        if items[i] < pivot:
            swap(left, i)
            left += 1
            i += 1
        elif items[i] > pivot:
            swap(i, right)
            right -= 1
        else:
            i += 1

    return items
