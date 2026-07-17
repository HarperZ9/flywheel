def is_balanced(s: str) -> bool:
    """
    Check if the given string s has balanced and correctly nested brackets.

    Args:
        s (str): The input string containing only parentheses, square brackets, and curly braces.

    Returns:
        bool: True if the brackets are balanced and correctly nested, False otherwise.
    """

    # Define a mapping of opening and closing brackets
    bracket_map = {'(': ')', '[': ']', '{': '}'}
    
    # Initialize an empty stack to keep track of opening brackets
    stack = []
    
    for char in s:
        if char in bracket_map:
            # If the character is an opening bracket, push it onto the stack
            stack.append(char)
        else:
            # If the character is a closing bracket
            if len(stack) > 0 and (bracket_map[stack.pop()] == char):
                continue
            else:
                return False
    
    # If the stack is empty, all brackets were correctly nested; otherwise, they are not balanced
    return len(stack) == 0
