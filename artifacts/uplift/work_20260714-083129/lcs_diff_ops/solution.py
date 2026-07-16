def diff_ops(a, b):
    if not (isinstance(a, list) and isinstance(b, list)):
        raise ValueError('bad input')
    
    def helper(i=0, j=0, prev='equal', items=[]):
        # Base case: both indices have reached the end of their respective lists
        if i == len(a) or j == len(b):
            return ((prev, items), None)
        
        key = (i, j, prev)
        if key in memo:
            return memo[key]
        
        res = helper(i + 1, j, 'equal', items)
        # Check for delete
        if prev != 'delete' and a[i] != b[j]:
            res = max(res, helper(i + 1, j, 'delete', [a[i]] + items), key=lambda x: len(x[1]))
        
        # Check for insert
        res = max(res, helper(i, j + 1, 'insert', [b[j]] + items), key=lambda x: len(x[1]))
        
        memo[key] = res
        return res
    
    memo = {}
    _, result = helper()
    
    if not result:
        return []
    
    # Coalesce consecutive operations with the same tag
    output = []
    for (tag, group) in result[0][1]:
        item_list = [elem for i, elem in enumerate(group)]
        output.append((tag, item_list))
    
    return output
