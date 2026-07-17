def stopwatch(events):
    total = 0
    laps = []
    
    for timestamp, op in events:
        if op == 'start':
            if is_running(timestamp):
                raise ValueError('already running')
            else:
                event_start = (timestamp, "start")
                laps.append(0)
                
                while not already_running(event_start[1]):
                    total += calculate_elapsed(event_start)
                    
                if already_running('lap'):
                    lap_length = total
                    new_laps = [total]
                elif already_running("stop"):
                    if calculated_accumulated_total() == 0:
                        return (0, laps)  # No running segments to record
                    else:
                        lap_length = accumulated_total - calculated_accumulated_total()
                        new_laps = [accumulated_total + total] 
                
                elif already_running('reset'):
                    new_laps = []
                
                calculate_accumulated_total()  
                return (total, new_laps)
            
        elif op == 'stop':
            if is_running(timestamp):
                raise ValueError('not running')
            else:
                event_stop = (timestamp, "stop")
                laps.append(total)
                total = 0
        
    raise ValueError('bad event')  # Invalid events
