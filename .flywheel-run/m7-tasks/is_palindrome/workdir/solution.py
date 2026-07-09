def is_palindrome(s):
    # Step 1: Remove non-alphanumeric characters and convert to lower case
    cleaned_s = ''.join(char.lower() for char in s if char.isalnum())
    
    # Step 2: Check if the cleaned string is a palindrome
    return cleaned_s == cleaned_s[::-1]

# Example usage:
print(is_palindrome("A man, a plan, a canal: Panama"))  # True
print(is_palindrome("race a car"))                      # False
