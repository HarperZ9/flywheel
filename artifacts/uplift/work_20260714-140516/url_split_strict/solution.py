def split_url(url):
    if not isinstance(url, str):
        raise ValueError('bad url')

    # Find scheme: everything before first ://
    colon_slash_slash = '://'
    scheme_end = url.find(colon_slash_slash)
    
    if scheme_end == -1:
        raise ValueError('no scheme')
    
    scheme = url[:scheme_end]
    
    if not scheme:
        raise ValueError('bad scheme')
    
    # Scheme validation: first char lowercase letter, rest a-z0-9+-.
    if not (ord(scheme[0]) >= ord('a') and ord(scheme[0]) <= ord('z')):
        raise ValueError('bad scheme')
    
    for c in scheme[1:]:
        allowed = [ord('a'), ord('z')] + \
                  [ord('0'), ord('9')] + \
                  [ord('+'), ord('-'), ord('.')]
        if not ((ord(c) >= allowed[0] and ord(c) <= allowed[1]) or
                (ord(c) >= allowed[2] and ord(c) <= allowed[3]) or
                (ord(c) == allowed[4])):
            raise ValueError('bad scheme')
    
    # Authority: everything after :// up to first / or ?
    auth_start = scheme_end + len(colon_slash_slash)
    
    if auth_start >= len(url):
        raise ValueError('no authority')
    
    path_start = url.find('/', auth_start)
    query_start = url.find('?', auth_start)
    
    # Find the earlier of the two
    if query_start != -1 and (path_start == -1 or query_start < path_start):
        auth_end = query_start
    else:
        auth_end = path_start
    
    authority = url[auth_start:auth_end]
    
    # Extract host and port from authority
    colon_in_auth = authority.rfind(':')
    
    if colon_in_auth != -1 and (colon_in_auth == len(authority) - 1):
        raise ValueError('bad port')  # Trailing colon
    
    host = None
    port_str = None
    
    if colon_in_auth != -1:
        host = authority[:colon_in_auth]
        
        possible_port = authority[colon_in_auth + 1:]
        
        # Port validation: must be digits, optional lone leading zero, <= 65535
        if not possible_port:
            raise ValueError('bad port')  # Empty port after colon
        
        if len(possible_port) > 1 and \
           possible_port[0] == '0' or \
           int(possible_port) > 65535 or \
           any(not c.isdigit() for c in possible_port):
            raise ValueError('bad port')
        
        port_str = possible_port
    else:
        if not authority.strip():
            raise ValueError('bad host')  # Empty authority
        host = authority
    
    # Host validation: a-z0-9-. must be non-empty
    if not (host and all(c.islower() or c.isdigit() or c in '-.' for c in host)):
        raise ValueError('bad host')
    
    port_int = int(port_str) if port_str else None
    
    # Path: from path_start to query_start, or / if none
    path = '/' if path_start == -1 else url[path_start:]
    
    # Query: everything after the first ?
    query = '' if (query_start == len(url) - 1 and '?' in path) or query_start == -1 \
            else None if query_start == -1 else url[query_start + 1:]
    
    return scheme
