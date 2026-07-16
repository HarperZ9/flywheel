def portal_moves(n, portals, start, goal):
    if n <= 1:
        raise ValueError('bad n')
    
    def calculate_min_steps(start_node, end_node, portal_locations):
        if start_node == end_node: 
            return 0

        min_steps = float("inf")
        
        for i in range(len(portals)):
            entry, exit = portals[i]
            next_nodes = []
            
            # Explore neighboring cells and check the validity
            for j in range(n):
                if (j - goal < 0 or start_node == portal_locations[goal][0] + j) \
                        and (j > 0 and end_node == portal_locations[start_node][1]):
                    next_nodes.append(portals[i])
                
                elif (j - goal == 0 or start_node == portal_locations[j][0]) \
                      and (start_node < portals[i][0] or end_node <= portals[i][1]):
                    continue

            # Calculate the minimum steps required for each valid neighbor
            if next_nodes:
                min_steps = min(min_steps, sum([abs(portal[1] - portal[2]) + calculate_min_steps(j, next_node, next_nodes) 
                                               for j in range(len(next_nodes))]))

        return min_steps

    portals_sorted = sorted(portals)
    start_node, goal_node = portals_sorted[start], portals_sorted[goal]
    
    # Validate start and end nodes
    if not (0 <= start < n and 0 <= goal < n) or \
       (start == goal_node and len(start_node) != len(goal_node)):
        raise ValueError('bad cell')

    # Calculate minimum steps between nodes
    return calculate_min_steps(start_node, goal_node, portals_sorted)
