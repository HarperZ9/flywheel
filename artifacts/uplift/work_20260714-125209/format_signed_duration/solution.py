def format_duration(seconds):
    if not isinstance(seconds, int) or isinstance(seconds, bool):
        raise ValueError("seconds must be an int and NOT a bool")
    is_negative = seconds < 0
    total_seconds = abs(seconds)
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    remaining_seconds = total_seconds % 60
    if hours >= 1:
        return f"-{hours}:{minutes:02d}:{remaining_seconds:02d}" if is_negative else f"{hours}:{minutes:02d}:{remaining_seconds:02d}"
    return f"{'-' if is_negative else ''}{total_seconds // 60}:{remaining_seconds:02d}"
