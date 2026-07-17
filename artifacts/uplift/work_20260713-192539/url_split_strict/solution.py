def split_url(url):
    if not isinstance(url, str):
        raise ValueError('bad url')
    
    scheme_end = url.find(':/')
    port_start = next((i for i, char in enumerate(url[scheme_end:]) if char == '/'), len(url))
    authority_end = min(port_start, url.rfind('?'))
    
    if ':' not in url[:scheme_end]:
        raise ValueError('no scheme')
    
    if any(not (isalpha(url[0]) or url[0] in '-._') for url_part in [url[:scheme_end], url[scheme_end+1:authority_end]]):
        raise ValueError('bad scheme')
    
    host = url[scheme_end+2:authority_end].strip('/:?')
    if not host:
        raise ValueError('bad host')
    
    if ':' in host and (not host.split(':', 1)[1].isdigit() or int(host.split(':', 1)[1]) > 65535):
        raise ValueError('bad port')
    
    path = '/' + url[authority_end+1:].strip('?/')
    
    if '?' not in url:
        query = None
    else:
        query_start = url.rfind('?') + 1
        query = url[query_start:authority_end].strip('?')
    
    return (url[:scheme_end], host, int(host.split(':', 1)[0]) if ':' in host else None, path[1:], query)
