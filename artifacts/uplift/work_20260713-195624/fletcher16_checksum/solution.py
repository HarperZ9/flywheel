def fletcher16(data):
    if not isinstance(data, str) and not isinstance(data, list):
        raise ValueError('bad input')
    
    if any(not isinstance(element, int) or element < 0 or element >= 256 for element in data):
        raise ValueError('bad byte')
        
    if not (all(0 <= element <= 255 for element in data)):
        raise ValueError('bad char')

    running_sum1 = running_sum2 = 0
    max_data_len = max(map(len, data))

    # Calculate the first running sum for each byte
    for i, value in enumerate(data):
        if i < len(data) - 1:
            running_sum1 += (value << 8) + data[i + 1]
        else:
            running_sum1 += value

    # Add the two sums modulo 256 to get the final checksum
    return ((running_sum1 * 256) + running_sum2) % 256
