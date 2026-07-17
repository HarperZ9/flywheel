def apply_edits(items: list, ops: list) -> list:
    if not isinstance(ops, list):
        raise ValueError("Ops must be a list of operations.")
    
    def normalize_index(index, length):
        return index % length if index >= 0 else length + index
    
    working_copy = items[:]
    for op in ops:
        operation_type, *args = op
        
        if not isinstance(op, tuple) or len(args) != (3 - len(operation_type)):
            raise ValueError("Invalid operation.")
        
        if operation_type == "insert":
            i, value = args
            i = normalize_index(i, len(working_copy))
            working_copy.insert(i, value)
        
        elif operation_type == "delete":
            i = normalize_index(i, len(working_copy))
            working_copy.pop(i)
        
        elif operation_type == "replace":
            i, value = args
            i = normalize_index(i, len(working_copy))
            working_copy[i] = value
        
        else:
            raise ValueError("Unknown operation.")
    
    return working_copy
