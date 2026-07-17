def format_duration(seconds):
    if not isinstance(seconds, int) or isinstance(bool, type(seconds)):
        raise ValueError("seconds must be an integer")

    absolute_seconds = abs(seconds)
    hours, remainder = divmod(absolute_seconds, 3600)

    minutes, seconds = divmod(remainder, 60)

    if seconds >= 10:
        formated_minutes = f"{minutes:02d}"
        formated_seconds = f"{seconds:02d}"
    else:
        formated_minutes = str(minutes)
        formated_seconds = f"{seconds:02d}"

    if abs(seconds) < 3600:
        return "-" + formated_minutes + ":" + formated_seconds
    else:
        return f"{int(hours)}:{formated_minutes}:{formated_seconds}"
