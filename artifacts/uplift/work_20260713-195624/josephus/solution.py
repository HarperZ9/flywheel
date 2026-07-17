def josephus(n: int, k: int) -> int:
    """
    Calculate the number of people left after eliminating every k-th person.

    :param n: The total number of people.
    :param k: Every k-th person is eliminated to calculate the survivor count.
    :return: The number of survivors after elimination.
    
    Raises ValueError if n < 1 or k < 1.
    """
    # If n or k are less than 0, raise a ValueError
    if n <= 0:
        raise ValueError("n must be greater than 0")
    if k <= 0:
        raise ValueError("k must be greater than 0")

    # Initialize the survivor count with the last person in the circle
    survivor_count = n
    
    # Start elimination from the last person
    for i in range(n - 1, -1, -1):
        if (i + 1) % k == 0:
            survivor_count -= 1

    return survivor_count
