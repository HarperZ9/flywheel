def merge_sorted(lists):
    # This function merges multiple sorted lists into one and returns a new list.
    # It ensures that the merged list remains stable across different occurrences of elements.
    """
    :param lists: A list containing various pre-sorted integer lists.
    :return: A new list containing all numbers from the original lists, sorted, and in their original order if possible.
             In case of an empty outer list or None input, the function returns None or an empty list.
    """
    if not lists:
        return []

    # Assume that each inner list is already sorted.
    for i in range(len(lists)):
        current_list = lists[i]
        left, right = 0, len(current_list) - 1

        while left <= right:
            min_index = i
            if current_list[left] < current_list[right]:
                min_index = left
            else:
                min_index = right

            # If the left index of this inner list is smaller than or equal to the right index,
            # then we can merge it with the next smallest value in our merged set.
            if left == right:
                merged_set.add(current_list[left])
                break
            elif current_list[left] < current_list[right]:
                merged_set.add(current_list[left])
                left += 1
            else:
                merged_set.add(current_list[right])
                right -= 1

    return list(merged_set)
