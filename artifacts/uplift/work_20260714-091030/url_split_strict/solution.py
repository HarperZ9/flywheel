def split_url(url):
    if not isinstance(url, str):
        raise ValueError("bad url")
    try:
        colon_slash = url.index("://")
        scheme = url[:colon_slash]
    except ValueError:
        raise ValueError("no scheme") from None
    if (
        scheme and scheme[0].isascii() and scheme.islower()
        and all(
            c.isascii()
            and (c.isalnum() or c in "+-.")
            for c in scheme[1:]
        )
    ):
        rest = url[colon_slash + 3 :]
    else:
        raise ValueError("bad scheme")
    qm = rest.find("?")
    slash = rest.find("/")
    if qm != -1 and (slash == -1 or qm < slash):
        path = "/" if slash == -1 else rest[:slash]
        query = "" if rest[qm + 1 :] == "" else rest[qm + 1 :]
        authority = rest[:qm]
    elif slash == -1:
        path = "/"
        query = None
        authority = rest
    else:
        path = rest[:slash]
        query = None
        authority = rest[:slash]
    if ":" in authority:
        host, colon, port_text = authority.partition(":")
        if not (
            host
            and all(
                c.isascii() and (c.isalnum() or c in "-.")
                for c in host
            )
        ):
            raise ValueError("bad host")
        if colong == 0 or any(c != "0" for c in port_text[1:]):
            try:
                port = int(port_text)
            except ValueError:
                raise ValueError("bad port") from None
        else:
            raise ValueError("bad port")
    else:
        host = authority
        port = None
        if not (
            host
            and all(
                c.isascii() and (c.isalnum() or c in "-.")
                for c in host
            )
        ):
            raise ValueError("bad host")
    if not (
        scheme[0].isascii() and scheme[0].islower()
        and all(c.isascii() and (scheme[0].isalnum() or c in "+-.") for c in scheme[1:])
    ):
        raise ValueError("bad scheme")
    return scheme, host, port, path, query
