def turtle(prog):
    def rotate(heading, direction):
        if heading == 'N' and direction in ['L', 'R']:
            return {'L': 'W', 'R': 'E'}[direction]
        elif heading == 'S' and direction in ['L', 'R']:
            return {'L': 'E', 'R': 'W'}[direction]
        elif heading == 'E' and direction in ['L', 'R']:
            return {'L': 'N', 'R': 'S'}[direction]
        elif heading == 'W' and direction in ['L', 'R']:
            return {'L': 'S', 'R': 'N'}[direction]
    
    x, y = 0, 0
    heading = 'N'
    for part in prog.split():
        count = ''
        
        # Check if the part is a number or command
        match part:
            case _ when part.isdigit():
                count += part
            case _ when part[0].isdigit() and not part[1:].isalpha():
                return ValueError('bad command')
    
        # If we have a count, reset it for next iteration if there's another part coming
        if count:
            continue
        
        match part:
            case 'F':
                x += yint(count) * dyint(heading)
                y -= yint(count) * dxint(heading)
            case 'B' | _ when part[0] in ['L', 'R']:
                heading = rotate(heading, part[1])
    
    return (x, y, heading)

from math import *
