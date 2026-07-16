import math

def grant_requests(capacity, events):
    """
    Simulates a token-bucket rate limiter and returns a list of bools indicating whether each request was granted.
    
    Each event is an (timestamp, amount) tuple. The timestamp must be non-decreasing.
    
    1. Validates that the capacity is at least 1.
    2. If events are not provided, or if they are a list and none of its elements match the correct format,
       raises ValueError('bad capacity') or IndexError
    3. The list of events must be non-empty for this function to work.
    
    Parameters:
    - capacity: An int representing the number of tokens the bucket can hold.
    - events: A list of (timestamp, amount) tuples, as described in the problem description.

    Returns:
    - A list of bools where True indicates the request was granted and False otherwise.
    """
    if not isinstance(capacity, int) or capacity <= 0:
        raise ValueError('bad capacity')
    
    if not events:
        return []
    
    if type(events) != list or len(events) == 0:
        raise IndexError
    
    for event in events:
        try:
            timestamp = max(event[0], events[-1][0])
            amount = min(capacity, event[1])
            
            # Validate the timestamp
            if not (timestamp >= events[0][0] and events[0][0] <= timestamp < events[-1][0]):
                raise ValueError('time warp')
                
            # Determine if a new bucket is needed
            bucket_size = capacity // math.ceil(timestamp / events[0][0])
            if amount > bucket_size:
                return [True]
            
            # Apply the refill in decreasing order of timestamps
            for i in range(events.index(event) + 1, len(events)):
                prev_timestamp = events[i - 1][0]
                
                # If we need to add more tokens up to the current timestamp
                if amount > bucket_size * (prev_timestamp // timestamp):
                    return [False]
                    
                remaining_tokens = max(bucket_size - amount, 0)
                amount -= min(remaining_tokens, bucket_size)
                
            # Grant the request, removing the required amount of tokens
            return [True] + [False] * (capacity - amount)
        except (IndexError, ValueError):
            raise IndexError
