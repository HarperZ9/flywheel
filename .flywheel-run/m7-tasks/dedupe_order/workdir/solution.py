def dedupe(items):
    seen = set()
    result = []
    
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
            
    return result

# Example usage:
items = [1, 2, 3, 4, 5, 2, 6, 7, 8, 9, 10, 1, 3]
print(dedupe(items))  # Output: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
