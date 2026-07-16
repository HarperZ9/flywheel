def search_rotated(nums, target):
    left, right = 0, len(nums)-1
    while left <= right:
        mid = (left + right) // 2
        if nums[mid] == target:
            return mid
        if nums[left] < nums[right]:
            # The list is not rotated and the element at mid must be less than or equal to the pivot
            if nums[left] <= target <= nums[mid]:
                right = mid - 1
            else:
                left = mid + 1
        elif nums[left] > nums[right]:
            # The list is rotated, so we need to find a position where nums[left] >= target and nums[mid+1] < target
            if nums[left] <= target:
                right = mid - 1
            else:
                left = mid + 1
        elif nums[left] == nums[right]:
            # If the pivot is equal, we need to check which side is larger
            if nums[left] >= target > nums[mid+1]:
                left = mid + 1
            else:
                right = mid - 1

    return -1
