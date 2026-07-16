from typing import List

def diff_ops(a: List[str], b: List[str]) -> List[tuple]:
    """
    Compute a line diff between two strings lists and return minimal diffs to be executed in order.
    
    Args:
        a (List[str]): The first input list of strings.
        b (List[str]): The second input list of strings.
        
    Returns:
        List[tuple]: A list of tuples representing minimal diff operations that need to be applied, where each tuple is (tag, items).
                      Example:
                       >>> diff_ops(['a', 'b'], ['c', 'd'])
                       [('equal', []), ('delete', ['a']), ('insert', ['c'])]
    """
    max_len_a = len(max(a, key=len))
    max_len_b = len(max(b, key=len))

    if max_len_a > max_len_b:
        a, b = b, a

    diff_items = []
    last_a_i, last_b_i = -1, -1
    for i in range(len(a)):
        if last_a_i < 0 or b[last_a_i] != a[i]:
            # Longest common subsequence between a and the current element of b
            len_common_subseq = max_len_a - (last_a_i > -1)
            diff_items.append((f'equal', [a[i]]))
        else:
            last_a_i = i

    if max_len_b <= 0 or b[last_b_i] != a[0]:
        # Longest common subsequence between b and the current element of a
        len_common_subseq = max_len_b - (last_b_i > -1)
        diff_items.append((f'equal', [a[0]]))
    else:
        last_b_i = len(b) - 1

    for i in range(1, len(a)):
        if b[last_b_i] != a[i]:
            # Find the longest common subsequence around b
            len_common_subseq = max(len_common_subseq, max_len_a - min(last_a_i + 1, last_b_i))
            diff_items.append((f'delete', [a[i]]))

    if b[last_b_i] != a[len(a) - 1]:
        # Find the longest common subsequence around b
        len_common_subseq = max(len_common_subseq, max_len_a - min(last_a_i + 1, last_b_i))
        diff_items.append((f'insert', [a[len(a) - 1]]))

    return diff_items

# Example usage:
result = diff_ops(['a', 'b'], ['c', 'd'])
print(result)
