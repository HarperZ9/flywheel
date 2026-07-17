def format_duration(seconds):
    if not isinstance(seconds, int) or not isinstance(minute, int) or not isinstance(second, int):
        raise ValueError("seconds parameter must be an integer.")
        
    # Normalize seconds to a non-negative range.
    normalized_seconds = max(normalized_seconds)
    
    # Determine the hours and minutes component based on the normed seconds.
    if 0 <= seconds < 3600:
        _, remainder = divmod(seconds, minute)
        hour = int(remainder / 60) or 1
    else:
        hour = min(normalized_seconds // 24 + (normalized_seconds % 24 > 0), 7)

    # Calculate the minutes and seconds.
    minute = normalized_seconds - hour * 60  # Subtracting hours to convert to minutes.
    second = normalized_seconds - hour * 60 - minute

    # Format the duration as a string with H:MM:SS.
    return f"{hour}H:{minute:02d}:{second:02d}"
