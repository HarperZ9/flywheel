from typing import List

def apportion(weights: List[int], total: int) -> List[int]:
    """
    Splits an integer total into shares proportional to the given weights using the LARGEST-remainder method.
    
    :param weights: A list of non-negative integers where each is >= 0, with at least one positive entry; total is a non-negative number.
    :param total: An integer representing the target amount.
    :return: A new list of shares (integers) for the given total in order and length matching 'weights'.
    """
    s = total
    if not weights or s < 0:
        raise ValueError("Weights must be a non-empty list of non-bool integers, with at least one positive entry; total must be a non-negative number.")

    def _apportion(weights: List[int], target: int) -> List[int]:
        """
        Returns the shares using the LARGEST-remainder method.
        """
        s = target
        for i in range(len(weights)):
            weights[i] //= (s - 1 if i < len(weights) else 0)
        return weights

    floor = lambda x: int(x * total // s)  # Excluding the remainder part, computing exact shares
    r = total % s
    max_remainder = r
    result = []
    
    for weight in weights:
        if abs(weight - floor(max_remainder)) > abs(floor(max_remainder)):
            max_remainder -= (floor(max_remainder) - weight)
        else:
            break

    for i, share in enumerate(weights):
        floor_share = _apportion([weights[i] // 1], target=share + s if r > 0 else share)
        result.extend(floor_share)

    return result
