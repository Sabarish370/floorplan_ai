import copy
from shapely.geometry import box
from layout.generator import build_floorplan, ROOM_DIMENSIONS
from layout.validator import validate_layout
from layout.architecture import validate_circulation_constraints
from layout.space_utilization import evaluate_space_utilization
from vastu.validator import analyze_vastu

def _is_adjacent(room_poly, gap_poly, tolerance=1.0):
    return room_poly.distance(gap_poly) <= tolerance

def evaluate_candidate_packing(rooms, reqs, plot_w, plot_d, facing):
    fp = build_floorplan(rooms, reqs, plot_w, plot_d, facing)
    
    # Hard geometry check
    if not validate_layout(fp)['valid']:
        return None
        
    # Hard circulation check
    circ_val = validate_circulation_constraints(fp)
    if not circ_val['valid']:
        return None
        
    # Hard Vastu check
    vastu_res = analyze_vastu(fp)
    if any(v['status'] == 'violation' for v in vastu_res['results']):
        return None
        
    # Hard Room Realism check
    from layout.architecture import evaluate_architecture
    arch = evaluate_architecture(fp)
    if arch.get('diagnostics', {}).get('room_realism_rejections', 0) > 0:
        return None
        
    space = evaluate_space_utilization(fp)
    
    # Minimize unused area and maximize coverage
    score = space['envelope_coverage_ratio'] - (space['largest_unused_region'] / (plot_w*plot_d)) * 50
    return score, fp, space

def optimize_global_footprint(candidate, reqs, plot_w, plot_d, facing, max_iterations=50):
    best_rooms = [r.model_dump() for r in candidate.rooms]
    res = evaluate_candidate_packing(best_rooms, reqs, plot_w, plot_d, facing)
    
    if res is None:
        return candidate, {}
        
    best_score, best_fp, best_space = res
    
    step_size = 2.0
    
    for _ in range(max_iterations):
        if best_space['envelope_coverage_ratio'] >= 95.0 and best_space['largest_unused_region'] < 10.0:
            break
            
        current_rooms = copy.deepcopy(best_rooms)
        space = evaluate_space_utilization(best_fp)
        gaps = space.get('unused_regions', [])
        
        if not gaps:
            break
            
        # Sort gaps by area descending
        gaps = sorted(gaps, key=lambda x: x['area'], reverse=True)
        largest_gap = gaps[0]
        
        # Build gap polygon
        gap_bbox = largest_gap['bbox']
        gap_poly = box(*gap_bbox)
        
        # Find adjacent rooms
        adjacent_rooms = []
        for idx, room in enumerate(current_rooms):
            if room['type'] == 'parking':
                continue
            room_poly = box(room['x'], room['y'], room['x'] + room['width'], room['y'] + room['depth'])
            if _is_adjacent(room_poly, gap_poly):
                adjacent_rooms.append(idx)
                
        improved = False
        
        for idx in adjacent_rooms:
            if improved:
                break
                
            room = current_rooms[idx]
            dims = ROOM_DIMENSIONS.get(room['type'], ROOM_DIMENSIONS['bedroom'])
            
            # Try operations
            operations = [
                # Expand X
                ('width', step_size, 0),
                ('width', step_size, -step_size), # expand left by shifting x
                # Expand Y
                ('depth', step_size, 0),
                ('depth', step_size, -step_size), # expand up by shifting y
                # Shift X
                ('x', step_size, 0),
                ('x', -step_size, 0),
                # Shift Y
                ('y', step_size, 0),
                ('y', -step_size, 0),
            ]
            
            for op, val, x_shift in operations:
                test_rooms = copy.deepcopy(current_rooms)
                test_room = test_rooms[idx]
                
                if op == 'width':
                    if test_room['width'] + val > dims.get('max_width', 100):
                        continue
                    test_room['width'] += val
                    if x_shift != 0:
                        test_room['x'] += x_shift
                elif op == 'depth':
                    if test_room['depth'] + val > dims.get('max_depth', 100):
                        continue
                    test_room['depth'] += val
                    if x_shift != 0:
                        test_room['y'] += x_shift
                elif op == 'x':
                    test_room['x'] += val
                elif op == 'y':
                    test_room['y'] += val
                    
                test_room['area'] = test_room['width'] * test_room['depth']
                
                # Boundary check
                if test_room['x'] < 0 or test_room['y'] < 0 or test_room['x'] + test_room['width'] > plot_w or test_room['y'] + test_room['depth'] > plot_d:
                    continue
                    
                res = evaluate_candidate_packing(test_rooms, reqs, plot_w, plot_d, facing)
                if res is not None:
                    new_score, new_fp, new_space = res
                    if new_score > best_score:
                        best_score = new_score
                        best_rooms = copy.deepcopy(test_rooms)
                        best_fp = new_fp
                        best_space = new_space
                        improved = True
                        break
                        
        if not improved:
            # If no single room move worked, try coordinated moves (swap, or push)
            pass
            
    return best_fp, best_space
