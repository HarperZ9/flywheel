def count_vowels(s):
    # Convert the input string to lowercase to make the search case-insensitive
    s = s.lower()
    
    # Define the set of vowels
    vowels = 'aeiou'
    
    # Initialize a counter for the number of vowels
    vowel_count = 0
    
    # Iterate through each character in the string and count if it is a vowel
    for char in s:
        if char in vowels:
            vowel_count += 1
            
    return vowel_count

# Example usage:
print(count_vowels("Hello World"))  # Output: 3
print(count_vowels("AEIOUaeiou"))   # Output: 10
