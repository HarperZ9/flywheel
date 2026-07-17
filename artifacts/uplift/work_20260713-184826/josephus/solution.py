def josephus(n, k):
    if n < 1 or k < 1:
        raise ValueError("n and k must be greater than 0")
    
    people = list(range(n))
    
    def eliminate(index, people):
        if len(people) == 1:
            return people[0]
        new_index = (index + k - 1) % len(people)
        people.pop(new_index)
        return eliminate(new_index, people)
    
    return eliminate(0, people)
# Example usage and test cases to verify the function
print(josephus(4, 2))  # Expected output: 1
print(josephus(5, 3))  # Expected output: 3
print(josephus(6, 5))  # Expected output: 0
