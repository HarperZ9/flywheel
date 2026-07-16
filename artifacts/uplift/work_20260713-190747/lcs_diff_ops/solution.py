def diff_ops(a, b):
    if not all(isinstance(x, str) for x in a + b):
        raise ValueError('bad input')

    def diff_lines(l1, l2, i=0, j=0, memo={}):
        key = (i, j)
        if key in memo:
            return memo[key]
        
        if i == len(l1) and j < len(l2):
            result = [('insert', [l2[j:]]), ('equal', [])]
        elif i < len(l1) and j == len(l2):
            result = [('delete', [l1[i:]])]
        else:
            if i < len(l1) and j < len(l2) and l1[i] == l2[j]:
                result = diff_lines(l1, l2, i + 1, j + 1)
                result.insert(0, ('equal', [l1[i]]))
            elif (i < len(l1) - 1 and
                  (j >= len(l2) or l1[i] == l1[i + 1]) and
                  (j < len(l2) - 1 and l2[j] != l2[j + 1])):
                result = [('delete', [l1[i], l1[i + 1]]),
                          diff_lines(l1, l2, i + 2, j)]
            elif (i >= len(l1) or l1[i] != l1[i - 1]) and \
                 (j < len(l2) - 1 and l2[j] == l2[j + 1]):
                result = [('insert', [l2[j], l2[j + 1]]),
                          diff_lines(l1, l2, i, j + 2)]
            else:
                result = [(('delete' if (i < len(l1) and
                                         j < len(l2) and l1[i] != l2[j]) else 'insert'),
                            [l1[i], l1[i]])]
            
        memo[key] = result
        return result

    return diff_lines(a, b)
