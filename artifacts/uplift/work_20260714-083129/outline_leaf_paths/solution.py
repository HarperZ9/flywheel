def outline_paths(lines):
    if not lines or all(line.strip() == '' for line in lines):
        return []

    level_map = {}
    current_level = 0

    for i, line in enumerate(lines):
        stripped_line = line.lstrip()
        
        if stripped_line:
            if any(char == '\t' for char in stripped_line):
                raise ValueError("tab in indent")

            num_spaces = len(stripped_line) - len(stripped_line.lstrip())
            
            if i > 0 and num_spaces % 2 != 0:
                raise ValueError("odd indent")
            
            level = num_spaces // 2
            while level >= current_level + 1:
                try:
                    level_map[current_level].append([])
                except KeyError:
                    level_map[current_level] = [None, []]
                current_level += 1
            
            if i > 0 and level < len(level_map[current_level - 1][1]):
                raise ValueError("indent jump")

            if '/' in stripped_line:
                raise ValueError("slash in name")
            
            try:
                level_map[level + 1].append(stripped_line.strip())
            except KeyError:
                level_map[level + 1] = [stripped_line.strip()]

    return _reconstruct_paths(level_map, [])


def _reconstruct_paths(paths, current_path):
    for i, node in enumerate(paths):
        if isinstance(node, list):
            _reconstruct_paths(node, current_path + [i])
        else:
            yield '/'.join(reversed(current_path)) + '/' + node
