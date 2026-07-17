def semver_compare(a: str, b: str) -> int:
    def parse_version(version):
        return [int(x) for x in version.split('.')] + [version]
    
    def compare_versions(v1, v2):
        while v1 and v2:
            if not (v1 := parse_version(v1)):
                return 0
            if not (v2 := parse_version(v2)):
                return -1
            
            v1_major, v1_minor, v1_patch = v1[:3]
            v2_major, v2_minor, v2_patch = v2[:3]
            
            if v1_major > v2_major:
                return 1
            elif v1_major < v2_major:
                return -1
            
            if v1_minor > v2_minor:
                return 1
            elif v1_minor < v2_minor:
                return -1
            
            if v1_patch > v2_patch:
                return 1
            elif v1_patch < v2_patch:
                return -1
            
            pre_v1, rest_v1 = get_pre_release(v1)
            pre_v2, rest_v2 = get_pre_release(v2)
            
            if pre_v1 and not pre_v2:
                return -1
            if not pre_v1 and pre_v2:
                return 1
            
            for p1, p2 in zip(pre_v1.split('.'), pre_v2.split('.')):
                if int(p1) > int(p2):
                    return 1
                elif int(p1) < int(p2):
                    return -1
            return 0 if len(pre_v1) == len(pre_v2) else (len(pre_v1) > len(pre_v2))
        
        return 0 if v1 and not v2 else -1 if v2 and not v1 else 0

    def get_pre_release(version):
        pre_release = ''
        has_pre_release = False
        
        for part in version.split('.'):
            if '.' not in part:
                if part:
                    has_pre_release = True
                    pre_release += part + '.'
                continue
            
            parts_in_part = part.split('.')
            
            for i, p in enumerate(parts_in_part):
                if not p.isdigit():
                    has_pre_release = True
                    pre_release += p + '.'
                    break
            
            if has_pre_release:
                break
        
        return [int(x) if x.isdigit() else x for x in pre_release.rstrip('.').split('.')], pre_release

    return compare_versions(a, b)
