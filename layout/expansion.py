from shapely.geometry import box
from config.architectural_config import ARCHITECTURAL_CONFIG
from config.room_dimensions import ROOM_DIMENSIONS

def expand_rooms(placed_rooms, plot_w, plot_d):
    expanded_rooms = []
    # Copy rooms
    for r in placed_rooms:
        expanded_rooms.append(r.copy())
        
    # Priority: Hall, Bedroom, Kitchen, Pooja, Bathroom
    def type_priority(t):
        if 'hall' in t: return 0
        if 'living' in t: return 0
        if 'bedroom' in t: return 1
        if 'kitchen' in t: return 2
        if 'dining' in t: return 3
        if 'pooja' in t: return 4
        return 5
        
    expanded_rooms.sort(key=lambda r: type_priority(r['type']))
    
    def intersect(r1, r2):
        # r1 and r2 are dicts with x, y, width, depth
        # AABB intersection
        return not (r1['x'] + r1['width'] <= r2['x'] + 0.01 or
                    r2['x'] + r2['width'] <= r1['x'] + 0.01 or
                    r1['y'] + r1['depth'] <= r2['y'] + 0.01 or
                    r2['y'] + r2['depth'] <= r1['y'] + 0.01)

    # Try to expand each room in 4 directions by step size
    step = 0.5
    changed = True
    iterations = 0
    while changed and iterations < 15: # reduced max iterations
        changed = False
        iterations += 1
        
        for room in expanded_rooms:
            if room['type'] in ['parking', 'circulation']:
                continue
                
            r_type = room['type'].split('_')[0]
            
            # Penalize extreme aspect ratios dynamically based on room type
            max_ratio = 2.5 if r_type in ['bathroom', 'hall', 'parking'] else 2.0
            
            dim_cfg = ROOM_DIMENSIONS.get(r_type, ROOM_DIMENSIONS['bedroom'])
            max_w = dim_cfg.get('max_width', plot_w)
            max_d = dim_cfg.get('max_depth', plot_d)
            
            def is_valid_expansion(w, d):
                if w > max_w or d > max_d: return False
                ratio = max(w, d) / min(w, d) if min(w, d) > 0 else 1.0
                if ratio > max_ratio: return False
                return True
            
            # Try growing right (+width)
            if is_valid_expansion(room['width'] + step, room['depth']) and room['x'] + room['width'] + step <= plot_w:
                test_box = {'x': room['x'], 'y': room['y'], 'width': room['width'] + step, 'depth': room['depth']}
                overlap = False
                for other in expanded_rooms:
                    if other['id'] != room['id'] and intersect(test_box, other):
                        overlap = True
                        break
                if not overlap:
                    room['width'] += step
                    room['area'] = room['width'] * room['depth']
                    changed = True
                    
            # Try growing down (+depth)
            if is_valid_expansion(room['width'], room['depth'] + step) and room['y'] + room['depth'] + step <= plot_d:
                test_box = {'x': room['x'], 'y': room['y'], 'width': room['width'], 'depth': room['depth'] + step}
                overlap = False
                for other in expanded_rooms:
                    if other['id'] != room['id'] and intersect(test_box, other):
                        overlap = True
                        break
                if not overlap:
                    room['depth'] += step
                    room['area'] = room['width'] * room['depth']
                    changed = True
                    
            # Try growing left (-x, +width)
            if is_valid_expansion(room['width'] + step, room['depth']) and room['x'] - step >= 0:
                test_box = {'x': room['x'] - step, 'y': room['y'], 'width': room['width'] + step, 'depth': room['depth']}
                overlap = False
                for other in expanded_rooms:
                    if other['id'] != room['id'] and intersect(test_box, other):
                        overlap = True
                        break
                if not overlap:
                    room['x'] -= step
                    room['width'] += step
                    room['area'] = room['width'] * room['depth']
                    changed = True
                    
            # Try growing up (-y, +depth)
            if is_valid_expansion(room['width'], room['depth'] + step) and room['y'] - step >= 0:
                test_box = {'x': room['x'], 'y': room['y'] - step, 'width': room['width'], 'depth': room['depth'] + step}
                overlap = False
                for other in expanded_rooms:
                    if other['id'] != room['id'] and intersect(test_box, other):
                        overlap = True
                        break
                if not overlap:
                    room['y'] -= step
                    room['depth'] += step
                    room['area'] = room['width'] * room['depth']
                    changed = True
                    
    # Snap alignment to reduce tiny slivers
    for r in expanded_rooms:
        r['x'] = round(r['x'], 2)
        r['y'] = round(r['y'], 2)
        r['width'] = round(r['width'], 2)
        r['depth'] = round(r['depth'], 2)
        
    return expanded_rooms
