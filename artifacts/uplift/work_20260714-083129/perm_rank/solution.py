def perm_rank(perm):
    if not isinstance(perm, list):
        raise ValueError('bad input')
    
    for element in perm:
        if not isinstance(element, int) or (isinstance(element, bool)):
            raise ValueError('bad element')
        
    n = len(perm)
    missing_values = [x for x in range(n) if x not in perm]
    extra_values = [x for x in perm if x >= n]

    if any(missing_values + extra_values):
        raise ValueError('not a permutation')

    def is_smaller(sublist1, sublist2):
        for item1, item2 in zip(sublist1, sublist2):
            if item1 < item2:
                return True
            elif item1 > item2:
                return False
        if len(sublist1) == len(sublist2):
            return False
        return True

    def rank_helper(perm_ranks, index, prev, count):
        if index == n:
            perm_ranks.append(count)
            return
        
        for value in range(len(perm)):
            if value not in perm_ranks:
                new_perm = perm[:]
                new_perm[index] = value
                if is_smaller(new_perm[:index + 1], prev) and len(set(new_perm)) == n:
                    count += rank_helper(perm_ranks, index + 1, new_perm, 0)
        return count

    perm.sort()
    perm_ranks = []
    rank_helper(perm_ranks, 0, [], 1)

    return perm_ranks[-1] - 1
