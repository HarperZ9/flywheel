def spiral_order(matrix):
    """
    This function takes a 2D matrix (list of lists) as input.
    It returns all elements of the matrix sorted in clockwise spiral order starting from the top-left corner.

    Parameters:
        - matrix: A 2D list of integers representing a square matrix

    Returns:
        - A list of integers representing the elements of the matrix in clockwise spiral order
    """
    n = len(matrix)
    
    if not (0 <= n <= 1):
        raise ValueError("The given input is an invalid square matrix")

    def direction(x, y, d):
        """
        Helper function to check if a move is valid and to get the next position based on the current point.
        
        Parameters:
            - x: The current row position
            - y: The current column position
            - d: The direction of movement (N, S, E, W)
            
        Returns:
            - A tuple representing the next position based on the current move
        """
        if d == "N":
            return [y + 1] * 20, [x]
        elif d == "S":
            return [y - 1], [x]
        elif d == "E":
            return [x + 1], [y]
        else: # W
            return [x - 1], [y]

    left, top = 0, 0
    right, bottom = n-1, len(matrix)-1

    result = []

    while True:
        if not (left <= right and top <= bottom):
            break

        move = direction(left, top, "N")
        r, c = move[0]
        left += 1
        right -= 1
        top += 1
        bottom -= 1
        
        result.append(matrix[r][c])

        if (right > left and bottom > top):
            continue

        if right >= left:
            if moving_from_left_to_right(right, bottom) or moving_from_above_to_below(left, right):
                break
