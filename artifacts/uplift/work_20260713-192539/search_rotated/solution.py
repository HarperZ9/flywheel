def search_rotated(nums, target):
    def binary_search(left, right):
        if left > right:
            return -1
        mid = (left + right) // 2
        if nums[mid] == target:
            return mid
        # Check if left side is sorted
        elif nums[left] <= nums[mid]:
            if nums[left] <= target < nums[mid]:
                return binary_search(left, mid - 1)
            else:
                return binary_search(mid + 1, right)
        # Right side must be sorted
        else:
            if nums[mid] < target <= nums[right]:
                return binary_search(mid + 1, right)
            else:
                return binary_search(left, mid - 1)

    return binary_search(0, len(nums) - 1)
