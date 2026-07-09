def max_of_three(a: int, b: int, c: int) -> int:
    if a >= b and a >= c:
        return a
    if b >= c:
        return b
    return c


def add(a: int, b: int) -> int:
    return a + b


def is_palindrome(s: str) -> bool:
    filtered = "".join(ch.lower() for ch in s if ch.isalnum())
    return filtered == filtered[::-1]


def count_vowels(s: str) -> int:
    vowels = {"a", "e", "i", "o", "u"}
    return sum(1 for c in s.lower() if c in vowels)


def fizzbuzz(n):
    out = []
    for i in range(1, n + 1):
        if i % 15 == 0:
            out.append("FizzBuzz")
        elif i % 3 == 0:
            out.append("Fizz")
        elif i % 5 == 0:
            out.append("Buzz")
        else:
            out.append(str(i))
    return out


def dedupe(items):
    seen = set()
    out = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def flatten_one(items):
    out = []
    for x in items:
        if isinstance(x, list):
            out.extend(x)
        else:
            out.append(x)
    return out
