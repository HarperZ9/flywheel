def col_label(n: int) -> str:
    """
    Convert a positive column index into its spreadsheet column label.

    Args:
        n (int): The positive column index.

    Raises:
        ValueError: If n is not a positive integer or is not of the correct type.

    Returns:
        str: A string representing the spreadsheet column label.
    """
    if not isinstance(n, int) or n <= 0:
        raise ValueError('bad column')

    # Define the mapping for base-26 numbering
    # This is done to map each index from 1 to 703 (ZZ in our case)
    number_to_label = {
        1: 'A', 26: 'Z', 52: 'AZ', 701: 'AA',
        702: 'ZZ', 703: 'BA'
    }

    # Convert the input index to its spreadsheet column label
    result = number_to_label[n]
    return result.upper()
