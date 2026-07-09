def rle_decode(s):
    out, i = [], 0
    while i < len(s):
        j = i
        while j < len(s) and s[j].isdigit():
            j += 1
        if j == i or j == len(s):
            raise ValueError(s[i:])
        n = int(s[i:j])
        if n == 0:
            raise ValueError(s[i:j])
        out.append(s[j] * n)
        i = j + 1
    return ''.join(out)
