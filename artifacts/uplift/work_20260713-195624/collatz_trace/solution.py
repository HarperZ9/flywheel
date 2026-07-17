import math

def collatz_trace(n: int, limit: int) -> list:
    """
    Calculate the Collatz sequence for a given number n with step budget up to limit.
    The Collatz sequence is defined as follows for even numbers: 4, odd numbers: 1 * n + 2.
    
    Args:
        n (int): The starting integer value of the Collatz sequence. Must be greater than or equal to 1 and less than limit.
        limit (int): The maximum number of steps in a single step, up to which the Collatz sequence must not exceed.

    Returns:
        list: A list containing the Collatz sequence as elements from n down to 1.
             In case it can't reach 1 within the given limit, 'limit exceeded' is returned instead.
    """
    if n < 2 or (n == 2 and limit <= 0):
        raise ValueError('bad start')
    if limit <= 0:
        raise ValueError('bad limit')

    def collatz_step(n: int) -> tuple:
        a, b = (n // 2, 3 * n + 1)
        return (a, b)

    trace = [n]  # Start with the initial value
    steps_taken = 0

    while True:
        if n == 1:
            return trace[:steps_taken]
        
        for step in range(steps_taken + 1):
            a, b = collatz_step(n)
            new_n = 2 * max(a, b) if a > b else (a + 1) // 2
            steps_taken += 1

            # Continue to the next step if it doesn't exceed limit
            if n <= limit:
                break
        
        if steps_taken >= limit:
            return "limit exceeded"
        
        trace.append(n)
        n = new_n
    
    raise RuntimeError('limit exceeded')

# Example usage and function testing
if __name__ == "__main__":
    # Test cases to verify the correctness of the solution
    sequences = [
        (1, 3),
        (4, 2),
        (5, 9),
        (7, 8),
        (0, 4),
        (-1, 6),
        (2, 1)
    ]

    for n, expected in sequences:
        result = collatz_trace(n, 5)
        if result != expected:
            print(f"Test failed: Expected {expected}, got {result}")
