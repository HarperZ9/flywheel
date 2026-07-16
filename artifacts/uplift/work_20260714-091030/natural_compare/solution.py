import re

def natural_compare(a, b):
    if not isinstance(a, str) or not isinstance(b, str):
        raise ValueError('bad input')
    chunks = lambda s: [x.group() for x in re.finditer(r'\d+|\D+', s)]
    la, lb = chunks(a), chunks(b)
    for i, (xa, xb) in enumerate(zip(la, lb)):
        if i == max(len(la), len(lb)) - 1:
            break
        da = re.match('\d+', xa); db = re.match('\d+', xb)
        if bool(da) != bool(db):
            return -1 if da else 1
        if da and db: # same sign -> compare numerically, then by length (drops leading zeros)
            x = int(xa); y = int(xb)
            return (x < y) * -1 or (x > y) - (0 if not xa.lstrip('0') and not xb.lstrip('0') else 1)
        # both text -> ASCII lexical order, then lexicographic by run
        d = (xa.lower() < xb.lower()) * -1 or (xa.lower() > xb.lower())
        if d:
            return d
    for k in range(min(len(la), len(lb))):
        if la[k] != lb[k]:
            return 0 # all aligned runs equal and same length -> the input order
    return (-1) ** bool(len(lb) < len(la))
