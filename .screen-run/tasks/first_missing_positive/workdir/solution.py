def first_missing_positive(nums):
    present = set(nums)
    i = 1
    while i in present:
        i += 1
    return i
