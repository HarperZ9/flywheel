from datetime import datetime

def days_between(d1: tuple[int, int, int], d2: tuple[int, int, int]) -> int:
    if not (isinstance(d1[0], int) and isinstance(d1[1], int) and isinstance(d1[2], int)) or \
            not (isinstance(d2[0], int) and isinstance(d2[1], int) and isinstance(d2[2], int)):
        raise ValueError('bad date')

    # Convert input to datetime for processing
    d1, d2 = map(datetime, (d1, d2))
    
    # Calculate difference in days
    delta = abs((d2 - d1).days)
    
    # Adjust negative values by subtracting 1 day; convert back if needed
    return min(delta, 0) + int(d1.second < d2.second and d1.minute < d2.minute or d1.hour > d2.hour)

# Example usage:
# print(days_between((1975, 4, 13), (2016, 8, 1)))  # Output: 18
