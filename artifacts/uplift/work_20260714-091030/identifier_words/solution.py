def split_identifier(s):
    if not s:
        return []
    out = []
    i = 0
    while i < len(s):
        if s[i] == '_':
            if out and out[-1].endswith('__'):
                raise ValueError('bad char')
            j = i + 1
            while j < len(s) and s[j] == '_':
                j += 1
            if out:
                if not any(c in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789' for c in s[i:j]):
                    raise ValueError('bad char')
                if out[-1]:
                    out[-1] += '_' * (j - i)
            i = j
        elif s[i].isalnum():
            j = i + 1
            while j < len(s) and s[j].isalnum():
                j += 1
            word = s[i:j]
            if not any(c in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789' for c in word):
                raise ValueError('bad char')
            first_uppers = start_upper(word)
            if len(first_uppers) == 1 and first_uppers[0] > 0:
                a, b = word[:first_uppers[0]], word[first_uppers[0]:]
                if out:
                    if out[-1].endswith('_'):
                        out[-1] += a
                    elif any(c in 'abcdefghijklmnopqrstuvwxyz' for c in out[-1]):
                        out[-1] += '_' + a
                    else:
                        out[-1] += a
                else:
                    out.append(a)
                i = j - len(word) + first_uppers[0]
            elif len(first_uppers) > 2 or len(first_uppers) == 2 and (first_uppers[1] != first_uppers[0] + 1):
                if not out or not any(c in 'abcdefghijklmnopqrstuvwxyz' for c in out[-1]):
                    raise ValueError('bad char')
                p = word
            elif len(s) > i:
                if 'abcdefghijklmnopqrstuvwxyz'.find(word.lower()) >= 0 and word.isupper():
                    raise ValueError('bad char')
                out.append(word)
                i += len(word)
        else:
            raise ValueError('bad char')
    return [x for x in out if any(c not in '_' for c in x)]

def start_upper(s):
    n = []
    for j in range(len(s)):
        if 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'.find(s[j]) >= 0 and (j == 0 or s[j - 1] != '_'):
            n.append(j)
    return n
