def two_sum(nums: List[int], target: int) -> List[int]:
    """
    两数之和：给定一个整数数组和目标值，找到所有满足下列条件的组合：
    给出的目标数字为target，并且两个索引i, j使nums[i] + nums[j] = target。
    返回所有的组合。如果存在多个这样的组合，将它们按照从小到大顺序输出。
    
    Args:
        nums: A list of integers.
        target: An integer that should be the sum of any two numbers in the returned list.
        
    Returns:
        A list of lists, each containing a pair of indices (i, j) such that nums[i] + nums[j] == target.
        If no such pairs exist or there are multiple valid pairs with the same index, return an empty list.
    """
    
    if not nums or len(nums) < 2:
        return []
    
    # 生成所有可能的组合
    for i in range(len(nums)):
        for j in range(i + 1, len(nums)):
            pair = [i, j]
            if sum(nums[i:j+1]) == target:
                return [pair] + two_sum(nums[j+1:], target - nums[i])
    
    # 如果没有找到这样的组合，返回空列表
    return []
