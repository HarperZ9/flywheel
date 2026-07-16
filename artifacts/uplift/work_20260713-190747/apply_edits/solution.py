def apply_edits(items, ops):
    """
    Applies a sequence of edit operations to a list purely.

    Args:
        items (list): The original list.
        ops (list): List of operations where each operation is a tuple or a string.

    Returns:
        list: A new list after applying the operations.
    """
    working_list = items[:]
    
    for op in ops:
        if not isinstance(op, tuple):
            raise ValueError(f"Operation must be a tuple, got {type(op)}")
        
        operation_name = op[0]
        if len(op) != 3 and (operation_name == "insert" or operation_name == "replace") or \
           len(op) != 2 and operation_name == "delete":
            raise ValueError(f"Invalid number of elements for {operation_name} operation")
        
        try:
            i = op[1]
            if i < 0:
                i += len(working_list)
            if operation_name == "insert":
                working_list.insert(i, op[2])
            elif operation_name == "delete":
                del working_list[i]
            elif operation_name == "replace":
                working_list[i] = op[2]
            else:
                raise ValueError(f"Unknown operation name: {operation_name}")
        except IndexError:
            raise IndexError("Index out of range") from None
    
    return working_list
