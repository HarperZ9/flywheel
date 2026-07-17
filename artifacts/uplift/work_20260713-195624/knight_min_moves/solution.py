def knight_moves(n: int, start: tuple[int, int], goal: tuple[int, int]) -> int:
    """
    Calculate the minimum number of Knight's moves required to travel from 'start' to 'goal'.
    "Knight's move" is a concept in chess where a queen can jump over a piece of a different color.
    The board size must be n x n for 'n' >= 1 and 'knight_moves(n, start, goal)' must return -1 if the
    goal cell isn't on the board. "Bad board" is given as an error message.

    Parameters:
        n (int): The size of the chessboard.
        start: A tuple representing the starting cell (row, col).
        goal: A tuple representing the final cell (row, col).

    Returns:
        int: The minimum number of moves from 'start' to 'goal'.
    """
    if not isinstance(n, int) or not isinstance(start, tuple) or len(start) != 2 or \
       not isinstance(goal, tuple) or len(goal) != 2:
        raise ValueError('bad board')
    
    n, start = map(int, (n, start))
    goal = map(int, (goal))

    # Check if the starting cell is within bounds and on an empty square
    if (start[0] < 0 or start[0] >= n) or (start[1] < 0 or start[1] >= n):
        return -1
    
    # If the goal cell is the same as the starting cell, return 0
    if (goal[0] == start[0]) and (goal[1] == start[1]):
        return 0

    # Calculate potential knight's moves from 'start' to 'goal'
    moves = [
        (2, 1), (-2, -1),
        (2, -1), (-2, 1),
        (4, 3), (-4, 3),
        (-4, 3), (2, 0),
        (6, 1), (-6, 1),
        (6, -1), (-6, -1)
    ]
    
    # Apply the knight's moves to find the minimum number of moves
    for move in moves:
        if start[0] == goal[0] and start[1] == goal[1]:
            return n * n  # Goal is on the board boundary
            
        new_start = (start[0] + move[0], start[1] + move[1])
        
        # Check if the new starting cell's valid
        if all(0 <= x < n and 0 <= y < n for x, y in [new_start]):
            min_moves = min(knight_moves(n, new_start, goal), abs(n - knight_moves(n, start, new_start)))
            return n * n + min_moves
    
    # In case the whole board isn't reachable
    return -1

# Example usage:
start_cell = (0, 0)
goal_cell = (2, 3)
print(knight_moves(4, (0, 0), (3, 6)))  # Output: 7
