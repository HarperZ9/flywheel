def round_half_even(num, den):
    """
    Rounds a rational number num by dividing it by its denominator den.
    
    Parameters:
    num (int): An exact rational number divided by any integer or non-integer.
    den (int): The denominator of the resulting fraction.

    Returns:
    int: The nearest integer that is either closer to 0 or closer to den without being exactly between them.
    """
    # Ensure inputs are integers and not bools, otherwise raise ValueError
    if not isinstance(num, int) or not isinstance(den, int):
        raise ValueError('bad arg')
    
    # Perform exact division
    exact_num = num / den
    
    # Determine the nearest even integer based on exact value of 0.5
    if exact_num == den:
        return exact_num - (exact_num % 1)
    elif exact_num == 0:
        return 0
    else:
        return round((exact_num + abs(0.5)) / 2)

# Test cases to verify the correctness of the function
def check_function():
    print("Testing")
    assert round_half_even(3, 4) == 1, "Test case 1 failed"
    assert round_half_even(-2.9, -8) == -2, "Test case 2 failed"
    assert round_half_even(0.5, 2) == 0, "Test case 3 failed"
    print("All test cases passed!")

check_function()
