def max_of_three(a, b, c):
    if a >= b and a >= c:
        return a
    elif b >= a and b >= c:
        return b
    else:
        return c

# Example usage:
print(max_of_three(10, 20, 30))  # Output: 30
print(max_of_three(-5, -10, -3))  # Output: -3
