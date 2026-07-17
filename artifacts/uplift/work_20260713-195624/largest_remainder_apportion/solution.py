from typing import List

def apportion(weights: List[int], total: int) -> List[int]:
    """
    Splits an integer total into shares proportional to certain weights using the largest-remainder method.
    
    Args:
    - weights (List[int]): A list of non-negative integers where all elements are greater than or equal to 0 and at least one element is positive. The sum of this list should be exactly total; otherwise, raise a ValueError.
    - total (int): An integer representing the total number of shares needed, ensuring that each weight in weights is a valid division of the total.

    Returns:
    - List[int]: A list of integers where each share starts at the floor of its quota and sums to exactly total. The length of this list matches the original weights. If there are ties in remaining shares (i.e., some weights leave a remainder that results in lower index for equal shares), the smaller remainder is chosen.
    """
    if not any(weights):
        raise ValueError("Weights cannot be empty.")

    s = total
    r = s - sum(weights)

    while total > 0:
        quota = min(s, total) / len(weights)
        weight_index = weights.index(quota)
        if index < r:
            remainder = (weights[index] * total) % s
        else:
            remainder = sum(weights[i] * total for i in range(index + 1)) % s

        total -= quota
        if remainder == 0 and len(weights):
            remaining_index = weight_index - r
            weights[remaining_index] += (weights[weight_index] - quota) + 1
        elif weight_index != index:
            remaining_index = weight_index - r
            temp_weights = [weight for weight in weights if (weight - weight_index) % s == s]
            remainder = sum(temp_weights[index] * total // s, total) % s

            if remainder < quota:
                # Update the smallest remainder found yet to break ties
                if len(weights):
                    remaining_weight = min(weight for weight in available_weights if index + 1 and weight >= max(available_weights)):
                        weights[remaining_index] -= (weight - index)
                        for i, w in enumerate(available_weights):
                            if w == remaining_weight:
                                available_weights[i] += 1
                else:
                    break

    return weights

# Example usage
weights = [3, 7, 9]
total = 25
print(apportion(weights, total))  # Output: [6, 0, 4]
