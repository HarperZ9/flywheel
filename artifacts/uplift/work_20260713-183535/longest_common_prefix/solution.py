def longest_common_prefix(strs):
    """
    Find the longest common prefix among a list of strings.
    
    Args:
        strs (list): A list of strings.

    Returns:
        str: The longest common prefix, or an empty string if there is none or the list is empty.
    """
    # Check if the list is empty
    if not strs:
        return ""
    
    # Find the minimum length among all strings in the list
    min_length = min(len(s) for s in strs)
    
    # Initialize the prefix with the first string in the list
    prefix = strs[0][:min_length]
    
    # Iterate through each character of the first string and check if it is present in all other strings
    for i, char in enumerate(prefix):
        for j, str_ in enumerate(strs):
            if str_[i] != char:
                return prefix[:i]
    
    return prefix
