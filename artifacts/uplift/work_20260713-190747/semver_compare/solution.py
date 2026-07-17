def semver_compare(a, b):
    def parse_version(version):
        parts = version.split('.')
        major = int(parts[0])
        minor = int(parts[1])
        patch = int(parts[2])
        pre_release = []
        if '-' in version:
            version, pre = version.split('-', 1)
            for part in pre.split('.'):
                try:
                    pre_release.append(int(part))
                except ValueError:
                    pre_release.append(part)
        return (major, minor, patch, tuple(pre_release))

    try:
        a_parsed = parse_version(a)
        b_parsed = parse_version(b)
    except IndexError:
        raise ValueError('bad version')
    
    if a_parsed > b_parsed:
        return 1
    elif a_parsed < b_parsed:
        return -1
    else:
        return 0
