import re

def split_url(url: str) -> tuple:
    """
    Split a URL into its components (scheme, host, port, path, query) based on valid separators.
    """
    if not url or type(url) != str:
        raise ValueError("bad url")
    
    # Regular expression for matching URLs
    regex = re.compile(r'^(?:https?://)'  # scheme: http or https
                      r'(?:\.[^/]*)@)?'
                      r'([^/]+)?:(.*)(?:/?[^\?]*)?$')  
    if not re.match(regex, url):
        raise ValueError('bad url')
    
    # Parse the URL into components based on valid separators and return them as a tuple
    parts = regex.split(url, 2) 
    scheme, host, port, path, query = parts[0], None, parts[1] if len(parts) > 1 else None
    
    while port is not None:
        try:
            port = int(port)
            break
        except ValueError:
            # Convert valid characters from the path to an integer
            port = re.match(r"^(?:\d{0,65}|[0-9][0-9]\d*)$", port).group(1)
    
    return scheme, host, port, path, query
