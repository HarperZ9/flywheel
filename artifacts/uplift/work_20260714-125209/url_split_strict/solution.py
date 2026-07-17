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
    
    # Host/port split at first :
    port_str = None
    colon_in_host = False
    
    if ':' in authority:
        col_idx = authority.find(':')
        
        if col_idx == len(authority) - 1 or \
           authority[:col_idx].endswith('..') or \
           '://' in authority[:col_idx]:
            # : at end -> no host, just port
            colon_in_host = False
        else:
            # Valid host:port split
            colon_in_host = True
            
            potential_port = authority[col_idx+1:]
            
            if not potential_port.isdigit():
                raise ValueError('bad port')
            
            p = int(potential_port)
            
            if p == 0 and len(potential_port) != 1:
                # Leading zero
                raise ValueError('bad port')
            
            if p > 65535:
                raise ValueError('bad port')
            
            port_str = str(p)
    
    host_start = 0
    
    if colon_in_host and ':' in authority:
        host_start = authority.find(':')
    
    host = authority[host_start:]
    
    # Host validation
    if not host:
        raise ValueError('bad host')
    
    for c in host:
        allowed = [ord('a'), ord('z')] + \
                  [ord('0'), ord('9')]
        
        if ord(c) == ord('-') or ord(c) == ord('.'):
            continue
        
        if not ((ord(c) >= allowed[0] and ord(c) <= allowed[1]) or
                (ord(c) == allowed[2])):
            raise ValueError('bad host')
    
    port = int(port_str) if port_str != None else None
    
    # Path: up to first ? after authority
    path_end = auth_end + url[auth_end:].find
