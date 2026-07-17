def interval_subtract(a, b):
    def valid(i):
        return i[0] <= i[1]
    if not all(map(valid, a + b)):
        raise ValueError('bad interval')
    out = []
    ba = iter(b)
    current = None
    bi = next(ba, None)
    for s, e in a:
        while bi is not None and bi[0] <= e:
            head = max(bi[0], s)
            tail = min(bi[1], e)
            if current is not None and current[1] + 1 >= head:
                current[1] = max(current[1], tail)
            else:
                if current is not None:
                    out.append(current)
                end = tail
                if end < s:   # b interval straddles neither of a's endpoints -> gap in a
                    out.append([head, end])
                current = [max(s, head + 1), e]
            if bi[1] >= e:
                break
            bi = next(ba, None)
        else:          # no overlap with b; extend surviving interval or start new
            if current is not None and current[1] + 1 == s:
                current[1] = e
            elif current is not None:
                out.append(current)
                current = [s, e]
    if current is not None:
        out.append(current)
    return out
