def parse_range_list(s):
    def process_range(range_str):
        if '-' not in range_str:
            return [int(range_str)]
        start, end = map(int, range_str.split('-'))
        return list(range(min(start, end), max(start, end) + 1))

    tokens = s.replace(' ', '').split(',')
    parsed_list = []
    
    for token in tokens:
        if '-' in token:
            parsed_list.extend(process_range(token))
        else:
            parsed_list.append(int(token))

    return sorted(set(parsed_list))
