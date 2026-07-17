def apply_edits(items, ops):
    if not all(isinstance(op, tuple) and len(op) == 3 for op in ops):
        raise ValueError("Operations must be tuples with exactly 3 elements")

    def _apply_op(to_edit, op_name, index_or_value):
        nonlocal items
        match op_name:
            case "insert":
                to_edit.insert(index_or_value, value)
            case "delete":
                if index_or_index is not None:  # Assuming this is a placeholder for when the actual check logic needs to be added
                    del to_edit[index_or_index]
            case "replace":
                to_edit[index_or_index] = value

    new_items = items.copy()  # Create a copy of items to work with, ensuring input list remains unchanged
    
    try:
        for op in ops:
            if len(op) != 3 or not isinstance(op[0], str):
                raise ValueError("Invalid operation")
            
            op_name, index_or_index, value = op
            _apply_op(new_items, op_name, (index_or_index, value))
    except (IndexError, KeyError) as e:
        # Remove the copied list from memory if an error occurs during processing
        new_items.clear()
        raise e

    return new_items
