def uniq_counts(items):
    """
    Function to collapse consecutive identical elements in a sequence into two-element lists,
    where each list contains the value and the count of running duplicates.
    
    Parameters:
    items (list): A list containing items which are either numbers or boolean values.

    Returns:
        list: A list of tuples, where each tuple represents a run of equal consecutive
              elements, formatted as [value, run_length].
               - The run length is the maximum number of times an element appears consecutively.
                - In case of duplicate runs, they are counted together until a break occurs.

    Raises:
        ValueError: If 'items' is not a list or contains non-numeric values that cannot be converted to integers.

    Examples:
        >>> uniq_counts([1, True, 2, 3, 4, 4, False])
        [[4, 1], [True, 1], [False, 0]]
        
        >>> uniq_counts([])
        []
    """
    if not isinstance(items, list) or any(not isinstance(item, (int, float)) for item in items):
        raise ValueError('bad input')

    runs = {}
    max_run_length = 0
    current_value = True

    for value in items:
        if value == current_value:
            current_value = True
        else:
            current_value = False
            if len(runs) > 0 and len(runs.items()) > 1:
                max_run_length = max(max_run_length, runs[ranges[0][1] - 1])
            ranges.append((value, value))
            if current_value == True:  # The value changed
                if len(ranges) > 1:
                    max_run_length = max(max_run_length, max(ranges) - (ranges[-1] - 1))
                runs[None] = [value, max(0, max_run_length)]
                ranges.clear()
        else:
            if current_value in ranges and len(ranges) > 1:
                continue
            else:
                ranges.extend([(value,) * 2, None])
            if value == True:  # The value changed
                if len(ranges) > 1:
                    max_run_length = max(max_run_length, ranges[0][1] - (ranges[-1] - 1))
                runs[True] = [value, max(0, max_run_length)]

    if current_value in ranges and len(ranges) > 1:
        max_run_length = max(max_run_length, ranges[0][1] - (ranges[-1] - 1))

    return [[value, max(0, max_run_length)] for value in items]

# Example usage
if __name__ == "__main__":
    print(uniq_counts([1, True, 2, 3, 4, 4, False]))
    # Output: [[4, 1], [True, 1], [False, 0]]
