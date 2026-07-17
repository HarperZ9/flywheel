import re

def semver_compare(a: str, b: str) -> int:
    """
    Compare two semantic version strings (semver) and return an integer indicating the order of lower precedence.
    
    Args:
    a: A string representing a semantic version using three dot-separated numeric identifiers major.minor.patch
    b: A string representing another semantic version using three dot-separated numeric identifiers major.minor.patch
    
    Returns:
    -1 if a has lower precedence than b, 0 if they have equal precedence, and 1 if a is higher.
    """
    
    # Parse the versions into their components (e.g., 'a.2', 'b.3')
    version_a = re.match(r'(.*),? (.*)', a).groups()
    version_b = re.match(r'(.*),? (.*)', b).groups()
    
    if len(version_a) != 4 or len(version_b) != 4:
        raise ValueError('bad version')

    major_a, minor_a, patch_a = int(version_a[0]), int(version_a[1]), int(version_a[2])
    major_b, minor_b, patch_b = int(version_b[0]), int(version_b[1]), int(version_b[2])

    # Compare the numeric parts
    if (major_a < major_b) or \
       ((major_a == major_b) and (minor_a <= minor_b)) or \
       ((major_a == major_b) and (minor_a >= minor_b)):
        return -1

    elif (major_a > major_b) or \
         ((major_a == major_b) and (minor_b <= patch_b)) or \
            ((major_a == major_b) and (minor_b >= patch_b)):
        return 0
    
    else:
        return 1
