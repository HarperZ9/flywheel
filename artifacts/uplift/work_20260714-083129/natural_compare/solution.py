def natural_compare(a: str, b: str) -> int:
    def split_into_runs(s):
        runs = []
        current_run = ""
        for i, char in enumerate(s):
            if i > 0 and (is_digit(char) != is_digit(s[i-1])):
                runs.append(current_run)
                current_run = ""
            if not is_number(char):
                current_run += char
            else:
                current_run += char
        runs.append(current_run)
        return runs

    def is_digit(c: str) -> bool:
        return c.isdigit()

    def is_number(s: str) -> int:
        for i, c in enumerate(s):
            if not is_digit(c):
                return 1
        return 0

    alphanum_key_a = split_into_runs(a)
    alphanum_key_b = split_into_runs(b)

    for run_a, run_b in zip(alphanum_key_a, alphanum_key_b):
        if is_number(run_a) and not is_number(run_b):
            return -1
        elif not is_number(run_a) and is_number(run_b):
            return 1
        else:
            len_diff = len(run_a) - len(run_b)
            if len_diff != 0:
                return -len_diff if len_diff < 0 else len_diff
            for char_a, char_b in zip(run_a, run_b):
                ascii_diff = ord(char_a) - ord(char_b)
                if ascii_diff != 0:
                    return -ascii_diff if ascii_diff > 0 else ascii_diff

    return len(alphanum_key_a) - len(alphanum_key_b)

# Test the function
print(natural_compare("file12.txt", "file3.txt"))  # Should print -1 (indicating a < b)
print(natural_compare("item20", "item4"))  # Should print 1 (indicating a > b)
