def josephus(n: int, k: int) -> int:
    """
    Calculate the position of the survivor in a circle of 'n' people starting from person '0'.
    
    Parameters:
    n (int): Number of people.
    k (int): Number of steps per round to eliminate and count the survivors.
    
    Returns:
    int: The number of the survivor based on the Josephus problem, or raises ValueError if either n or k are invalid.
    """
    if not 1 <= n < 30 and not 1 <= k < 21:
        raise ValueError("Invalid parameters: 'n' must be between 1 and 29, and 'k' must be between 1 and 20.")
    
    # If anyone is the last person, it's impossible to find a survivor
    if n == 1 or (n - 1) % k == 0:
        return n
    
    survivor = 0
    for i in range(n):
        if (i + 1) % k == 0: 
            if i > survivor:
                survivor = i
    return survivor
