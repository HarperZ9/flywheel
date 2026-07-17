def apply_edits(items: list, ops: list) -> list:
    """
    Apply a sequence of edit operations to a list in Python.

    Parameters:
    items (list): A list that should not be modified.
    ops (list): A list containing valid operation tuples, where each tuple is one type of operation

    Returns:
    list: The new list after applying all operations.

    Note:
    1. Valid operation types are:
       - Insert at index i with value "value"
       - Delete the element at index i
       - Replace the element at index i with value "value"

    In each valid operation, indices are evaluated against the current working copy of the list.
    """
    try:
        for op in ops:
            if not isinstance(op[0], tuple) or len(op) != 3:
                raise ValueError("Invalid operation: only 'insert', 'delete' and 'replace' operations allowed")
            
            # Modify index range
            if not (isinstance(op[1], int) and 0 <= op[1] < len(items)) or\
               not (isinstance(op[2], str)):
                raise ValueError("Invalid operation: indices must be in the range [0, n-1]")

            item = items.copy()
            if isinstance(op[0], tuple):
                op[0] = "insert" + str(item.index(op[1])) + " " + str(op[2])
            elif isinstance(op[0], list) or isinstance(op[0], int):
                raise ValueError("Invalid operation: indices must be in the range [0, n-1]")
            else:
                item.pop(index="delete", n=1)
            
            items = item

        return items
    except IndexError:
        # Normal insert index out of bounds is allowed.
        return items

# Test cases to verify correctness
def check_operations():
    assert apply_edits([1, 2], [("insert", 5, "a"), ("delete", 0), ("replace", 4, "b ")]) == [1, 4, 6]
    assert apply_edits([1, 2, 3, 4], [("insert", 1, 0), ("replace", 0, 9)]) == [1, 2, 9, 3, 4]
    print("All test cases passed!")

check_operations()
