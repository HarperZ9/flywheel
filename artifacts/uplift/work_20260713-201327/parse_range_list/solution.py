def parse_range_list(s):
    """
    Parse a string like '1-3,5,7-9' into the sorted deduplicated list of integers it denotes ([1,2,3,5,7,8,9]).
    Ranges are inclusive and may overlap each other or single values. Whitespace around commas/tokens is allowed.
    An empty or whitespace-only string returns [].

    Args:
        s (str): A string in the format 'num1,num2,...' where num1... can be integers with ranges [1..N].

    Returns:
        list: The sorted deduplicated list of integers.
    """
    # Split the input string by commas
    elements = s.split(',')
    
    # Define a set to store unique numbers
    unique_numbers_set = set()
    
    # Process each element in the split list
    for element in elements:
        num, _, _, _, _, _ = element.strip().split('-')
        
        # Convert the string to an integer and add it to the set if not already present
        unique_numbers_set.add(int(num))
    
    return sorted(unique_numbers_set)
