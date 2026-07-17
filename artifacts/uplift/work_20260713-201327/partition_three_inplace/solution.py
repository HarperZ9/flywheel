def partition_three(items: List[int], pivot: int) -> List[int]:
    """
    Reorders a list of integers in place around a given pivot.

    Args:
        items (List[int]): A list of integers to be partitioned.
        pivot (int): An integer that will divide the list into three sublists,
                     with all elements less than `pivot` in the first sublist, 
                     equal to `pivot` in the second, and greater than
                     `pivot` in the third.

    Returns:
        List[int]: The reordered list of integers.
    """
    left, right = 0, len(items) - 1

    while left <= right:
        if items[left] < pivot:  # element less than pivot
            items[left], items[right] = items[right], items[left]
            right -= 1  # decrease the comparison count and move to the next element in the sorted subarray
        
        else:
            left += 1  # move the current element to its correct position (pivot is already in the correct spot)

    return items

# A check function with provided data points
def check_partition_three():
    assert partition_three([4, 5, 6, -2, 8], 3) == [4, -2, 5, 6, 8]
    assert partition_three([-1, -100, 0, 0, 0], -1) == [-1, 0, 0, 0, -1]
    assert partition_three([1, 3, 2, 4, 5], 5) == [1, 2, 3, 4, 5]

check_partition_three()
