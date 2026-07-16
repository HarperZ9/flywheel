def split_url(url):
    if not isinstance(url, str):
        raise ValueError('bad url')
    
    def parse_scheme(url):
        scheme, *rest = url.partition(':')
        if not scheme or not scheme[0].islower() or any(c.isupper() or c in set('-._') for c in scheme[1:]):
            raise ValueError('bad scheme')
        return scheme
    
    def parse_authority(scheme_url):
        parts = scheme_url.split('/')
        host, *rest = parts[:-1]
        port = None
        if len(parts) > 2 and ':' in parts[-1]:
            host, port_str, query = '/', '', None
            port_index = parts[-1].find(':')
            port_str = parts[-1][:port_index]
            query_start = port_index + 1
            while query_start < len(parts[-1]) and parts[-1][query_start] in '?#':
                if query is not None:
                    break
                if parts[-1][query_start] == '?':
                    query = parts[-1][query_start+1:]
                query_start += 1
            port_index = port_str.find(':')
            try:
                port = int(port_str[:port_index])
            except ValueError:
                raise ValueError('bad port') from None
        host = ''.join(map(str.strip, filter(None, (host + '/' + part if part != '' else '') for part in reversed(host.split('//'))))
        return host, port, query
    
    scheme_url, authority, *path_query = url.partition('?')
    scheme = parse_scheme(scheme_url)
    host, port, query = parse_authority(authority or '/')
    return (scheme, host, port, path_query[0] if len(path_query) == 1 else '', query)
