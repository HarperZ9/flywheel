def split_url(url):
    if not isinstance(url, str):
        raise ValueError('bad url')
    
    parts = url.split('://', 1)
    if len(parts) == 2:
        scheme, rest = parts
    else:
        raise ValueError('no scheme')
    
    if not scheme or not scheme[0].islower() or not all(c.isalnum() or c in '+-. ' for c in scheme[1:]):
        raise ValueError('bad scheme')
    
    authority, path = '', '/'
    rest, query = rest.split('?', 1) if '?' in rest else (rest, '')
    if '#' in query:
        query, _ = query.split('#', 1)
    
    if '//' in rest:
        authority, path = rest.lstrip('/').split('/', 1)
    
    if ':' in authority:
        host, port_str = authority.rsplit(':', 1)
        try:
            port = int(port_str)
            if port < 0 or port > 65535 or (port == 0 and len(host) != 0):
                raise ValueError
        except ValueError:
            raise ValueError('bad port')
    else:
        host, port = authority, None
    
    if not host or not all(c.isalnum() or c in '-.' for c in host.replace('[', '').replace(']', '')):
        raise ValueError('bad host')
    
    return (scheme, host, port, path, query)
