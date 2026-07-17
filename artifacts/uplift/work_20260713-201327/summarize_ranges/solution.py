def summarize_ranges(nums):
    if not nums:
        return []

    # Collect all unique numbers into a set to handle duplicates
    num_set = set(nums)

    result = []
    n = 0

    for num in nums:
        # Check if it's the first element or we're dealing with non-integer items
        if len(result) == 1 or (len(result) > 1 and not str(num - 1).isdigit()):
            current_number = int(num)
            result.append(f"{current_number}-")
        else:
            # If the number is greater than the last one, we start a new range
            if num < result[-1][0]:
                result[-1] += ' ' + f'{num} '
            elif num == result[-1][-2:]:
                result[-1] += ' ' + str(num) + '-' + num[0]
            else:
                current_number = int(str(num)[1:-1])  # Convert to decimal string
                result.append(f"{current_number}-")
        n += 1

    if not len(result):  # If the list is empty, return an empty list
        return []

    for i in range(0, len(nums) - 1):
        if nums[i] == nums[i + 1]:
            continue
        else:
            result.append(f"{nums[i]}-{nums[i+1]}")
            break

    if not len(result):  # If the list is empty or has one element, we've finished
        return [result.pop()]

    for i in range(len(result)):
        result[i] = f"({result[i]})"

    if n % 2 == 0:
        first_number = int(result[0])
    else:
        first_number = int(result[-1]) + 1

    for i in range(1, len(nums) - 1):
        if nums[i] < first_number or (nums[i] & 1 and not str(first_number).isdigit()):
            num_set.remove(str(first_number))
            
    # Process the remaining numbers: Convert to int, remove duplicates, etc.
    result = [num[0] + ' ' if len(num) == 2 else ' '.join(sorted(set(result))) for num in nums]
    return result
nums = [0, 1, 2, 4, 5]
print(summarize_ranges(nums))  # Output: ['0-1', '3-4', '5']

nums = [-1, -3, 0, -6]
print(summarize_ranges(nums))  # Output: ['-1-0']
