def semver_compare(a: str, b: str) -> int:
    def parse_version(ver):
        parts = ver.split('.')
        for i in range(len(parts)):
            parts[i] = int(parts[i])
        return tuple(parts)
    
    def compare_parts(part1, part2):
        if isinstance(part1, int) and isinstance(part2, int):
            return cmp(part1, part2)
        elif isinstance(part1, int):
            return -1
        elif isinstance(part2, int):
            return 1
        else:
            return cmp(part1, part2)
    
    def pre_release_cmp(pre1, pre2):
        p1_parts = [int(i) if i.isdigit() else i for i in pre1.split('.')]
        p2_parts = [int(i) if i.isdigit() and not i.replace('.', '').isdigit() else i for i in pre2.split('.')]
        
        for part1, part2 in zip(p1_parts, p2_parts):
            cmp_result = compare_parts(part1, part2)
            if cmp_result != 0:
                return -cmp_result
        return len(p1_parts) - len(p2_parts)
    
    v1_parsed = parse_version(a)
    v2_parsed = parse_version(b)
    
    # Compare major version numbers first.
    for i in range(min(len(v1_parsed), len(v2_parsed))):
        cmp_result = compare_parts(v1_parsed[i], v2_parsed[i])
        if cmp_result != 0:
            return -cmp_result
    
    # Check pre-release
    cmp_result = pre_release_cmp(*v1_parsed[len(v1_parsed):len(v2_parsed)], *v2_parsed[len(v2_parsed):])
    return -cmp_result if cmp_result < 0 else cmp_result
