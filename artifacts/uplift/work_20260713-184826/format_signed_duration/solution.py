def format_duration(seconds):
    if not isinstance(seconds, int) or isinstance(seconds, bool):
        raise ValueError("seconds must be an integer and not a boolean")
    
    if seconds < 0:
        return '-' + _format_duration(-seconds)
    else:
        return _format_duration(seconds)

def _format_duration(seconds):
    if seconds >= 3600:
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        seconds = seconds % 60
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    else:
        minutes = seconds // 60
        seconds %= 60
        return f"{minutes}:{seconds:02d}"

# Example usage:
# print(format_duration(3661))  # Output: "1:01:01"
# print(format_duration(-86400)) # Output: "-1:00:00"
