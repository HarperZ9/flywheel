import re

def unfold_headers(lines: list[str]) -> list[tuple[str, str]]:
    """
    Unfolds email/HTTP-style header lines into a nested tuple of (name, value) tuples.
    
    Args:
        lines (list[str]): A list containing physical lines from an HTTP or email style headers.
        
    Returns:
        list[tuple[str, str]]: A nested tuple representing the unfolded headers in ORDERED COLUMNS.
    """
    if len(lines) == 0:
        raise ValueError("No logical lines available.")
    
    name = None
    values = []
    for line in lines:
        # Check if the current line is a continuation of an existing header
        if not line.strip().startswith("  "):
            if name and values:
                if name != "" and len(values) == 1:
                    yield tuple(values), name + ": "
                else:
                    raise ValueError(f"Invalid header: {values}")
                
                names = [name] + list(filter(None, re.split(r'[\s-]+', line)))
                if not names[-1]:  # Check for empty name
                    raise ValueError("Empty headers")
            
            name = None
        values.append(line.strip())
    
    if name and len(values) == 1:
        yield tuple(values), name + ": "
    else:
        raise ValueError(f"Invalid header: {values}")

# Example usage:
headers = [
    "HTTP/1.1 200 OK\r\nDate: Fri, 9 Dec 2023 06:00:00 GMT\r\n",
    "",
    "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4758.82 Safari/537.36",
    "",
    "X-Auth-Token:\r\nAuthorization: Bearer \u0017\ud83c\u7589\u00b4\xbb\xae",
    "",
    "Content-Type: text/plain\r\n"
]

unfold_headers(headers)
