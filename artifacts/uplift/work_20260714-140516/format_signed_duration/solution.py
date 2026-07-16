def format_duration(seconds):
    if not isinstance(seconds, int) or isinstance(seconds, bool):
        raise ValueError("seconds must be an int and NOT a bool")
    is_negative = seconds < 0
    total_seconds = abs(seconds)
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    remaining_seconds = total_seconds % 60
    if hours >= 1:
        formatted = f"{hours}:{minutes:02d}:{remaining_seconds:02d}"
    else:
        formatted = f"{minutes}:{remaining_seconds:02d}"
    return "-" + formatted if is_negative else formatted
