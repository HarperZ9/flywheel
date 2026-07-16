def josephus(n: int, k: int) -> int:
    """
    Returns the position of the last remaining person in a Josephus problem scenario.
    The function raises a ValueError for invalid inputs n and k.
    """
    if n < 1 or k < 1:
        raise ValueError("Number of people and interval must be greater than zero.")
    
    def josephus_rec(n: int, k: int) -> int:
        if n == 1:
            return 0
        else:
            position = (josephus_rec(n - 1, k) + k) % n
            return position
    
    return josephus_rec(n, k)
