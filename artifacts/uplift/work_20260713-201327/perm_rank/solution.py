def perm_rank(perm):
    """
    Returns the 0-based rank of a permutation in the lexicographic ordering of all permutations of 0..n-1.
    
    Parameters:
    perm (list): A list representing the input permutation, containing every integer from 0 to len(perm)-1 exactly once.
                 The elements must be integers and not bools.

    Returns:
    int: The rank of the permutation as an integer starting from 0 or -n! if it's the last element in a longer tuple. 
         Example for [0, 2, 1] is 4, as the permutations are 0-2-1 and 2-1-0.
    """
    
    if not perm:
        raise ValueError('bad input')
        
    n = len(perm)
    
    # Check if all elements in the permutation are integers or bools
    if any(not isinstance(x, int) for x in perm):
        raise ValueError('bad element')
    
    # Check if the list is a valid permutation of 0..n-1
    if perm != sorted(range(n), key=lambda i: perm[i]):
        raise ValueError('not a permutation')
    
    # Calculate and return the rank based on lexicographic order
    return n - perm.index(perm[-1])
