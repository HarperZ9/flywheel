def format_duration(seconds):
    if not isinstance(seconds, int) or isinstance(seconds, bool):
        raise ValueError("Input must be an integer and cannot be a boolean")

    abs_seconds = abs(seconds)
    minutes, seconds = divmod(abs_seconds, 60)
    hours, minutes = divmod(minutes, 60)

    if seconds >= 3600:
        return f"{int(hours)}:{minutes:02d}:{seconds:02d}"
    else:
        return f"{'-' if seconds < 0 else ''}{int(hours):01d}:{minutes:02d}:{seconds:02d}"
