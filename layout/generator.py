from models.requirements import FloorPlanRequirements
from models.floorplan import FloorPlan, Room
from config.room_dimensions import ROOM_DIMENSIONS
from utils.normalization import normalize_room_name
from geometry.geometry_utils import boxes_intersect, get_shared_edge
from layout.adjacency import get_room_adjacency_preferences
from layout.entrance import create_main_entrance, create_vehicle_gate
from layout.doors import generate_internal_doors
from vastu.zones import get_zone, get_zone_coverage
from vastu.rules import VASTU_RULES
import random
import math
from layout.expansion import expand_rooms
from layout.orientation import normalize_orientation, get_boundary_coordinate, is_room_on_boundary


def get_vastu_penalty(x, y, w, d, r_type, plot_w, plot_d, facing):
    coverage = get_zone_coverage(x, y, w, d, plot_w, plot_d)
    
    # Check if this room type has a rule
    rule = next((r for r in VASTU_RULES if r['room_type'] == r_type), None)
    if not rule:
        # Check master bedroom special case
        if r_type == 'master_bedroom':
            rule = next((r for r in VASTU_RULES if r['room_type'] == 'master_bedroom'), None)
        else:
            return 0
            
    if not rule:
        return 0
        
    p_zones = rule.get('preferred_zones', [])
    a_zones = rule.get('acceptable_zones', [])
    av_zones = rule.get('avoid_zones', [])
    
    penalty = 0
    # Severe penalty if footprint intersects avoid zones
    if any(z in av_zones for z, cov in coverage.items() if cov > 0.05):
        penalty += 1000
        
    if av_zones and not p_zones and not a_zones:
        # Only avoid rules
        pass
    else:
        p_coverage = sum(cov for z, cov in coverage.items() if z in p_zones)
        a_coverage = sum(cov for z, cov in coverage.items() if z in a_zones)
        
        if p_coverage > 0:
            penalty -= (p_coverage * 100)
        elif a_coverage > 0:
            penalty -= (a_coverage * 50)
        else:
            penalty += 100 # Not in any preferred or acceptable zone
            
    return penalty

def generate_layout(reqs: FloorPlanRequirements, seed: int = 0, strategy: str = 'baseline', root_variant: str = 'A', is_root_generation: bool = False) -> FloorPlan:
    plot_w = reqs.plot.width
    plot_d = reqs.plot.depth
    facing = reqs.plot.facing.lower()
    
    rng = random.Random(seed) if seed != 0 else None
    
    placed_rooms = []
    
    # STEP 3: Reserve parking
    if reqs.parking or reqs.rooms.get('parking', 0) > 0:
        dims = ROOM_DIMENSIONS.get('parking', ROOM_DIMENSIONS['bedroom'])
        w, d = dims['pref_width'], dims['pref_depth']
        
        facing_norm = normalize_orientation(facing)
        axis, min_val, max_val, target_val = get_boundary_coordinate(facing_norm, plot_w, plot_d)
        
        if root_variant == 'B':
            if axis == 'x':
                best_pos = (target_val - w if target_val > 0 else 0, plot_d - d, w, d)
            else:
                best_pos = (plot_w - w, target_val - d if target_val > 0 else 0, w, d)
        else:
            if axis == 'x':
                best_pos = (target_val - w if target_val > 0 else 0, 0, w, d)
            else:
                best_pos = (0, target_val - d if target_val > 0 else 0, w, d)
            
        placed_rooms.append({
            'id': 'parking_1', 'type': 'parking', 'name': 'Parking',
            'x': float(best_pos[0]), 'y': float(best_pos[1]), 
            'width': float(best_pos[2]), 'depth': float(best_pos[3]),
            'area': float(best_pos[2] * best_pos[3])
        })
        
    # STEP 4: Place hall
    hall_count = reqs.rooms.get('hall', 0)
    if hall_count > 0:
        dims = ROOM_DIMENSIONS.get('hall', ROOM_DIMENSIONS['bedroom'])
        plot_area = plot_w * plot_d
        scale = math.sqrt(plot_area / 1200.0)
        
        facing_norm = normalize_orientation(facing)
        axis, min_val, max_val, target_val = get_boundary_coordinate(facing_norm, plot_w, plot_d)
        
        if reqs.parking:
            pr_w = ROOM_DIMENSIONS.get('parking', {})['pref_width']
            pr_d = ROOM_DIMENSIONS.get('parking', {})['pref_depth']
            if axis == 'y':
                w = float(plot_w - pr_w)
                d = max(float(dims['pref_depth']), round((float(dims['pref_depth']) * scale) / 2) * 2)
                if plot_d >= 45:
                    d = max(d, min(24.0, round((plot_d * 0.45) / 2) * 2))
                d = min(d, plot_d * 0.48)
            else:
                w = max(float(dims['pref_width']), round((float(dims['pref_width']) * scale) / 2) * 2)
                w = min(w, plot_w - pr_w)
                d = max(float(dims['pref_depth']), round((float(dims['pref_depth']) * scale) / 2) * 2)
                d = min(20.0, d)
                d = min(d, plot_d * 0.45)
        else:
            w = max(float(dims['pref_width']), round((float(dims['pref_width']) * scale) / 2) * 2)
            d = max(float(dims['pref_depth']), round((float(dims['pref_depth']) * scale) / 2) * 2)
            w = min(w, plot_w * 0.65)
            d = min(d, plot_d * 0.48)
            
        w = max(12.0, w - (w % 2))
        d = max(14.0, d - (d % 2))
        
        # Anchor hall strictly to the frontage boundary
        candidates = []
        
        if axis == 'x':
            x_options = [target_val - w if target_val > 0 else 0]
            if reqs.parking:
                pr_w = ROOM_DIMENSIONS.get('parking', {})['pref_width']
                if target_val == 0: x_options.append(pr_w)
                else: x_options.append(plot_w - pr_w - w)
                
            for x in x_options:
                for y in range(0, int(plot_d - d) + 1, 2):
                    c = {'x': float(x), 'y': float(y), 'width': float(w), 'depth': float(d)}
                    if not any(boxes_intersect(c, pr) for pr in placed_rooms):
                        road_dist = abs(x - target_val) if target_val == 0 else abs(x + w - target_val)
                        dist = road_dist * 100 + y
                        candidates.append((dist, c))
        else:
            y_options = [target_val - d if target_val > 0 else 0]
            if reqs.parking:
                pr_d = ROOM_DIMENSIONS.get('parking', {})['pref_depth']
                if target_val == 0: y_options.append(pr_d)
                else: y_options.append(plot_d - pr_d - d)
                
            for y in y_options:
                for x in range(0, int(plot_w - w) + 1, 2):
                    c = {'x': float(x), 'y': float(y), 'width': float(w), 'depth': float(d)}
                    if not any(boxes_intersect(c, pr) for pr in placed_rooms):
                        road_dist = abs(y - target_val) if target_val == 0 else abs(y + d - target_val)
                        dist = road_dist * 100 + x
                        candidates.append((dist, c))
                    
        # Fallback if frontage is somehow completely blocked
        if not candidates:
            ideal_cx = (plot_w / 2) - (w / 2)
            ideal_cy = (plot_d / 2) - (d / 2)
            for x in range(0, int(plot_w - w) + 1, 2):
                for y in range(0, int(plot_d - d) + 1, 2):
                    c = {'x': float(x), 'y': float(y), 'width': float(w), 'depth': float(d)}
                    if not any(boxes_intersect(c, pr) for pr in placed_rooms):
                        dist = (x - ideal_cx)**2 + (y - ideal_cy)**2
                        # Prevent centering from creating unusable <12ft strips on BOTH sides
                        if (0 < x < 12) and (0 < (plot_w - (x + w)) < 12):
                            dist += 10000
                        if (0 < y < 12) and (0 < (plot_d - (y + d)) < 12):
                            dist += 10000
                        candidates.append((dist, c))
                        
        if candidates:
            candidates.sort(key=lambda item: item[0])
            if rng:
                top_n = min(len(candidates), 5)
                best_c = rng.choice(candidates[:top_n])[1]
            else:
                best_c = candidates[0][1]
            cx, cy = best_c['x'], best_c['y']
        else:
            cx, cy = 0.0, 0.0
        
        placed_rooms.append({
            'id': 'hall_1', 'type': 'hall', 'name': 'Hall 1' if hall_count > 1 else 'Hall',
            'x': float(cx), 'y': float(cy), 
            'width': float(w), 'depth': float(d),
            'area': float(w * d)
        })
        
        for i in range(1, hall_count):
            pass # Skipping multiple halls for prototype simplicity

    # STEP 5: Main entrance will be handled via create_main_entrance later, but we know it connects to hall_1
    
    # Collect other rooms
    other_rooms = []
    
    # Add rooms in specified priority based on strategy
    priority = ['bedroom', 'kitchen', 'bathroom', 'pooja', 'dining', 'utility']
    
    if strategy == 'pooja_first':
        priority = ['pooja', 'kitchen', 'bedroom', 'bathroom', 'dining', 'utility']
    elif strategy == 'kitchen_first':
        priority = ['kitchen', 'pooja', 'bedroom', 'bathroom', 'dining', 'utility']
    elif strategy == 'vastu_first':
        priority = ['pooja', 'kitchen', 'bedroom', 'bathroom', 'dining', 'utility']
    elif strategy == 'bedroom_first':
        priority = ['bedroom', 'bathroom', 'kitchen', 'pooja', 'dining', 'utility']
    elif strategy == 'bathroom_avoidance':
        priority = ['bathroom', 'pooja', 'kitchen', 'bedroom', 'dining', 'utility']
    elif strategy == 'balanced':
        priority_core = ['pooja', 'kitchen', 'bedroom', 'bathroom']
        if rng:
            rng.shuffle(priority_core)
        priority = priority_core + ['dining', 'utility']
    
    for p in priority:
        count = reqs.rooms.get(p, 0)
        norm_type = normalize_room_name(p)
        for i in range(count):
            other_rooms.append({'type': norm_type, 'name': f'{norm_type.capitalize()} {i+1}' if count > 1 else norm_type.capitalize(), 'id': f'{norm_type}_{i+1}'})
            
    # Add any remaining
    for r_type, count in reqs.rooms.items():
        if r_type == 'hall' or r_type in priority: continue
        norm_type = normalize_room_name(r_type)
        for i in range(count):
            other_rooms.append({'type': norm_type, 'name': f'{norm_type.capitalize()} {i+1}' if count > 1 else norm_type.capitalize(), 'id': f'{norm_type}_{i+1}'})
            
    # Do not shuffle all other_rooms entirely, as it breaks the strategy priority
    # and causes large rooms to be placed last when no perimeter space remains,
    # leading to room_count_rejections. Instead, rely on anchor sampling for diversity.
            
    # Place other rooms
    hall_r = next((r for r in placed_rooms if r['type'] == 'hall'), None)
    
    for room in other_rooms:
        r_type = room['type']
        dims = ROOM_DIMENSIONS.get(r_type, ROOM_DIMENSIONS['bedroom'])
        w = dims['pref_width']
        d = dims['pref_depth']
        
        # Phase 3G.5: Maximize footprint
        env_x_min, env_x_max = 0, plot_w
        env_y_min, env_y_max = 0, plot_d
        
        candidates = []
        for x in range(int(env_x_min), int(env_x_max - w) + 1, 2):
            for y in range(int(env_y_min), int(env_y_max - d) + 1, 2):
                c = {'x': float(x), 'y': float(y), 'width': float(w), 'depth': float(d)}
                
                # Check overlap
                if any(boxes_intersect(c, pr) for pr in placed_rooms):
                    continue
                    
                # Phase 3G.4: Compact footprint enforcement
                # Must share an edge with ANY connected room (excluding parking) to maintain compactness
                connected = False
                for pr in placed_rooms:
                    if pr['type'] == 'parking':
                        continue
                    edge = get_shared_edge(c, pr)
                    if edge:
                        edge_len = max(abs(edge['x2'] - edge['x1']), abs(edge['y2'] - edge['y1']))
                        if edge_len >= 3.0: # Minimum door width
                            connected = True
                            break
                            
                if not connected and len([r for r in placed_rooms if r['type'] != 'parking']) > 0:
                    continue
                
                # We want to minimize distance to Hall as a secondary metric to maintain compactness
                hx = hall_r['x'] + hall_r['width']/2 if hall_r else plot_w/2
                hy = hall_r['y'] + hall_r['depth']/2 if hall_r else plot_d/2
                dist = (x + w/2 - hx)**2 + (y + d/2 - hy)**2
                
                if strategy != 'baseline':
                    v_penalty = get_vastu_penalty(x, y, w, d, r_type, plot_w, plot_d, facing)
                    
                    # Target-zone constrained placement
                    if v_penalty <= 0: # Inside a preferred ( -100 ) or acceptable ( -50 ) or neutral ( 0 ) zone
                        candidates.append(((v_penalty, dist), c))
                    elif strategy == 'balanced': # balanced allows avoided zones with penalty
                        candidates.append(((v_penalty, dist), c))
                else:
                    candidates.append(((0, dist), c))
                            
        if candidates:
            candidates.sort(key=lambda item: item[0])
            if rng:
                top_n = min(len(candidates), 5)
                best_c = rng.choice(candidates[:top_n])[1]
            else:
                best_c = candidates[0][1]
                
            placed_rooms.append({
                'id': room['id'], 'type': room['type'], 'name': room['name'],
                'x': float(best_c['x']), 'y': float(best_c['y']), 
                'width': float(best_c['width']), 'depth': float(best_c['depth']),
                'area': float(best_c['width'] * best_c['depth'])
            })
            
            # 5. Remaining-space feasibility check
            placed_area = sum(r['area'] for r in placed_rooms)
            total_req_area = 0
            for r in reqs.rooms:
                total_req_area += ROOM_DIMENSIONS.get(r, ROOM_DIMENSIONS['bedroom'])['pref_width'] * ROOM_DIMENSIONS.get(r, ROOM_DIMENSIONS['bedroom'])['pref_depth'] * reqs.rooms[r]
            
            # If remaining plot area is less than remaining required area, this placement is dead
            if (plot_w * plot_d) - placed_area < (total_req_area - placed_area):
                break # abort this candidate generation early
            
    total_req_rooms = sum(count for r, count in reqs.rooms.items() if r != 'parking')
    placed_non_parking = len([r for r in placed_rooms if r['type'] != 'parking'])
    need_beam_search = False
    if not is_root_generation:
        if placed_non_parking < total_req_rooms:
            need_beam_search = True
        else:
            test_doors = generate_internal_doors(placed_rooms)
            if len(test_doors) < total_req_rooms - 1:
                need_beam_search = True

    if need_beam_search:
        beam_plans, _ = generate_layout_beam_search(reqs, strategy=strategy if strategy != 'baseline' else 'balanced')
        if beam_plans:
            return beam_plans[0]
            
    from shapely.geometry import box
    from shapely.ops import unary_union
    polygons = [box(r['x'], r['y'], r['x'] + r['width'], r['y'] + r['depth']) for r in placed_rooms if r['type'] != 'parking']
    built_area = unary_union(polygons).area if polygons else 0.0
    plot_area = plot_w * plot_d
    
    entrance = create_main_entrance(plot_w, plot_d, facing, placed_rooms)
    vehicle_gate = create_vehicle_gate(plot_w, plot_d, facing, placed_rooms)
    doors = generate_internal_doors(placed_rooms)
    
    rooms_models = [Room(**r) for r in placed_rooms]
    
    return FloorPlan(
        plot_width=plot_w,
        plot_depth=plot_d,
        plot_area=plot_area,
        built_area=built_area,
        utilization_percentage=(built_area / plot_area) * 100 if plot_area > 0 else 0,
        facing=facing,
        rooms=rooms_models,
        doors=doors,
        entrance=entrance,
        vehicle_gate=vehicle_gate
    )

def generate_room_candidates(room_info, placed_rooms, reqs, plot_w, plot_d, facing, strategy, max_candidates=10, room_diagnostics=None):
    r_type = room_info['type']
    r_type_base = r_type.split('_')[0]
    dims = ROOM_DIMENSIONS.get(r_type, ROOM_DIMENSIONS['bedroom'])
    plot_area = plot_w * plot_d
    
    # Adaptive sizing based on plot capacity and room type
    sizes = []
    base_w, base_d = float(dims['pref_width']), float(dims['pref_depth'])
    
    if r_type_base == 'bedroom':
        if plot_area >= 1800:
            sizes = [(16.0, 14.0), (14.0, 16.0), (14.0, 14.0), (12.0, 14.0), (14.0, 12.0), (12.0, 12.0)]
        elif reqs.rooms.get('bedroom', 0) == 1 and plot_area >= 1100:
            sizes = [(16.0, 14.0), (14.0, 16.0), (16.0, 16.0), (18.0, 14.0), (14.0, 14.0)]
        else:
            sizes = [(10.0, 14.0), (10.0, 12.0), (14.0, 12.0), (12.0, 14.0), (14.0, 14.0), (12.0, 12.0), (16.0, 12.0)]
            if plot_area <= 1200 or plot_w <= 28:
                sizes = [(10.0, 12.0), (12.0, 10.0), (10.0, 10.0), (10.0, 14.0), (14.0, 10.0), (11.0, 11.0)]
    elif r_type_base == 'kitchen':
        if plot_area >= 1800:
            sizes = [(14.0, 12.0), (12.0, 12.0), (12.0, 10.0), (10.0, 12.0), (10.0, 10.0), (14.0, 14.0)]
        elif reqs.rooms.get('bedroom', 0) == 1 and plot_area >= 1100:
            sizes = [(12.0, 12.0), (14.0, 12.0), (12.0, 14.0), (10.0, 10.0)]
        else:
            sizes = [(10.0, 10.0), (12.0, 10.0), (10.0, 12.0)]
            if plot_area <= 1200 or plot_w <= 28:
                sizes = [(10.0, 10.0), (10.0, 8.0), (8.0, 10.0), (9.0, 10.0), (12.0, 10.0)]
    elif r_type_base == 'bathroom':
        if plot_area >= 1800:
            sizes = [(10.0, 8.0), (8.0, 10.0), (8.0, 8.0), (10.0, 10.0), (8.0, 6.0), (6.0, 8.0)]
        elif reqs.rooms.get('bedroom', 0) == 1 and plot_area >= 1100:
            sizes = [(10.0, 8.0), (8.0, 10.0), (8.0, 8.0), (10.0, 10.0), (8.0, 6.0), (6.0, 8.0)]
        else:
            sizes = [(6.0, 8.0), (8.0, 6.0), (6.0, 6.0), (8.0, 8.0)]
            if plot_area <= 1200 or plot_w <= 28:
                sizes = [(5.0, 7.0), (7.0, 5.0), (6.0, 6.0), (6.0, 7.0), (5.0, 8.0), (6.0, 8.0)]
    elif r_type_base == 'pooja':
        sizes = [(6.0, 6.0), (6.0, 8.0), (8.0, 6.0), (4.0, 6.0)]
        if plot_area <= 1200 or plot_w <= 28:
            sizes = [(4.0, 5.0), (5.0, 4.0), (4.0, 6.0), (4.0, 4.0), (6.0, 6.0)]
    else:
        sizes = [(base_w, base_d)]
        if base_w != base_d:
            sizes.append((base_d, base_w))
    
    if room_diagnostics is not None and r_type not in room_diagnostics:
        room_diagnostics[r_type] = {
            "candidate_positions_generated": 0,
            "preferred_zone_candidates_generated": 0,
            "acceptable_zone_candidates_generated": 0,
            "neutral_zone_candidates_generated": 0,
            "preferred_zone_candidates_rejected": 0,
            "acceptable_zone_candidates_rejected": 0,
            "neutral_zone_candidates_rejected": 0,
            "top_rejection_reasons": {"overlap": 0, "connectivity": 0, "topology": 0}
        }
    
    candidates = []
    hall_r = next((r for r in placed_rooms if r['type'] == 'hall'), None)
    circ_r = next((r for r in placed_rooms if r['type'] == 'circulation'), None)
    
    # Determine allowed parent rooms for adjacency
    if r_type.startswith('bedroom'):
        parent_rooms = ([circ_r] if circ_r else []) + ([hall_r] if hall_r else [])
    elif r_type.startswith('kitchen'):
        parent_rooms = ([hall_r] if hall_r else []) + ([circ_r] if circ_r else [])
        parent_rooms += [pr for pr in placed_rooms if pr['type'].startswith('kitchen')]
    elif r_type.startswith('pooja'):
        parent_rooms = ([hall_r] if hall_r else []) + ([circ_r] if circ_r else [])
        parent_rooms += [pr for pr in placed_rooms if pr['type'].startswith('kitchen')]
    elif r_type.startswith('bathroom'):
        parent_rooms = [hall_r] if hall_r else []
        if circ_r:
            parent_rooms.append(circ_r)
        bedrooms_with_bath = set()
        for pr in placed_rooms:
            if pr['type'].startswith('bathroom'):
                for br in placed_rooms:
                    if br['type'].startswith('bedroom') and get_shared_edge(pr, br):
                        edge = get_shared_edge(pr, br)
                        if edge and max(abs(edge['x2'] - edge['x1']), abs(edge['y2'] - edge['y1'])) >= 3.0:
                            bedrooms_with_bath.add(br['id'])
        parent_rooms += [pr for pr in placed_rooms if pr['type'].startswith('bedroom') and pr['id'] not in bedrooms_with_bath]
    else:
        parent_rooms = [pr for pr in placed_rooms if pr['type'] != 'parking']

    def get_parent_adjacent_positions(parents, w, d):
        pos_set = set()
        for p in parents:
            if not p: continue
            px, py, pw, pd = float(p['x']), float(p['y']), float(p['width']), float(p['depth'])
            # 1. South of parent
            y = py + pd
            if y <= plot_d - d:
                x_min = max(0, int(px - w + 3.0))
                x_max = min(int(plot_w - w), int(px + pw - 3.0))
                if x_min <= x_max:
                    for x_val in [px, px + pw - w, 0.0, float(plot_w - w), float(x_min), float(x_max)]:
                        if x_min <= x_val <= x_max:
                            pos_set.add((float(x_val), float(y)))
                    for step_x in range(x_min, x_max + 1, 2):
                        pos_set.add((float(step_x), float(y)))
            # 2. North of parent
            y = py - d
            if y >= 0:
                x_min = max(0, int(px - w + 3.0))
                x_max = min(int(plot_w - w), int(px + pw - 3.0))
                if x_min <= x_max:
                    for x_val in [px, px + pw - w, 0.0, float(plot_w - w), float(x_min), float(x_max)]:
                        if x_min <= x_val <= x_max:
                            pos_set.add((float(x_val), float(y)))
                    for step_x in range(x_min, x_max + 1, 2):
                        pos_set.add((float(step_x), float(y)))
            # 3. East of parent
            x = px + pw
            if x <= plot_w - w:
                y_min = max(0, int(py - d + 3.0))
                y_max = min(int(plot_d - d), int(py + pd - 3.0))
                if y_min <= y_max:
                    for y_val in [py, py + pd - d, 0.0, float(plot_d - d), float(y_min), float(y_max)]:
                        if y_min <= y_val <= y_max:
                            pos_set.add((float(x), float(y_val)))
                    for step_y in range(y_min, y_max + 1, 2):
                        pos_set.add((float(x), float(step_y)))
            # 4. West of parent
            x = px - w
            if x >= 0:
                y_min = max(0, int(py - d + 3.0))
                y_max = min(int(plot_d - d), int(py + pd - 3.0))
                if y_min <= y_max:
                    for y_val in [py, py + pd - d, 0.0, float(plot_d - d), float(y_min), float(y_max)]:
                        if y_min <= y_val <= y_max:
                            pos_set.add((float(x), float(y_val)))
                    for step_y in range(y_min, y_max + 1, 2):
                        pos_set.add((float(x), float(step_y)))
        return list(pos_set)

    for w, d in sizes:
        positions = get_parent_adjacent_positions(parent_rooms, w, d)
        if not positions:
            # Fallback to bounded grid scan if no adjacent candidate was generated
            positions = [(float(x), float(y)) for x in range(0, int(plot_w - w) + 1, 2) for y in range(0, int(plot_d - d) + 1, 2)]
            
        for x, y in positions:
            c = {'x': float(x), 'y': float(y), 'width': float(w), 'depth': float(d)}
            
            v_penalty = get_vastu_penalty(x, y, w, d, r_type, plot_w, plot_d, facing) if strategy != 'baseline' else 0
            
            if room_diagnostics is not None:
                room_diagnostics[r_type]["candidate_positions_generated"] += 1
                if v_penalty <= -100:
                    room_diagnostics[r_type]["preferred_zone_candidates_generated"] += 1
                elif v_penalty <= -50:
                    room_diagnostics[r_type]["acceptable_zone_candidates_generated"] += 1
                else:
                    room_diagnostics[r_type]["neutral_zone_candidates_generated"] += 1

            if any(boxes_intersect(c, pr) for pr in placed_rooms):
                if room_diagnostics is not None:
                    room_diagnostics[r_type]["top_rejection_reasons"]["overlap"] += 1
                    if v_penalty <= -100: room_diagnostics[r_type]["preferred_zone_candidates_rejected"] += 1
                    elif v_penalty <= -50: room_diagnostics[r_type]["acceptable_zone_candidates_rejected"] += 1
                    else: room_diagnostics[r_type]["neutral_zone_candidates_rejected"] += 1
                continue
                
            # Direct hall / circulation connection check
            connected_to_hall = False
            connected_to_circ = False
            valid_passage_connection = False
            if hall_r:
                edge = get_shared_edge(c, hall_r)
                if edge and max(abs(edge['x2'] - edge['x1']), abs(edge['y2'] - edge['y1'])) >= 3.0:
                    connected_to_hall = True
                    valid_passage_connection = True
            if circ_r:
                edge = get_shared_edge(c, circ_r)
                if edge and max(abs(edge['x2'] - edge['x1']), abs(edge['y2'] - edge['y1'])) >= 3.0:
                    connected_to_circ = True
                    valid_passage_connection = True
            
            # Check connection to other placed rooms
            connected_to_other = False
            for pr in placed_rooms:
                if pr['type'] == 'parking': continue
                edge = get_shared_edge(c, pr)
                if edge and max(abs(edge['x2'] - edge['x1']), abs(edge['y2'] - edge['y1'])) >= 3.0:
                    connected_to_other = True
                    pr_base = pr['type'].split('_')[0]
                    if pr_base in ['dining', 'living', 'hall', 'circulation']:
                        valid_passage_connection = True
                    elif pr_base == 'bedroom' and r_type.startswith('bathroom'):
                        valid_passage_connection = True
                    elif pr_base == 'kitchen' and (r_type.startswith('pooja') or r_type.startswith('kitchen')):
                        valid_passage_connection = True
                        if r_type.startswith('pooja'):
                            connected_to_hall = True
                            
            connected = connected_to_hall or connected_to_circ or connected_to_other
            
            # Enforce strictly: bedroom MUST connect directly to Hall OR Circulation
            if r_type.startswith('bedroom') and not (connected_to_hall or connected_to_circ):
                continue
                
            # Kitchen MUST connect to Hall OR Circulation (unless wet kitchen attached to another kitchen)
            if r_type.startswith('kitchen') and not (connected_to_hall or connected_to_circ):
                is_secondary_kitchen = any(pr['type'].startswith('kitchen') for pr in placed_rooms 
                                           if get_shared_edge(c, pr) and max(abs(get_shared_edge(c, pr)['x2'] - get_shared_edge(c, pr)['x1']), abs(get_shared_edge(c, pr)['y2'] - get_shared_edge(c, pr)['y1'])) >= 3.0)
                if not is_secondary_kitchen:
                    continue
            
            if not connected and len([r for r in placed_rooms if r['type'] != 'parking']) > 0:
                continue
            
            hx = hall_r['x'] + hall_r['width']/2 if hall_r else plot_w/2
            hy = hall_r['y'] + hall_r['depth']/2 if hall_r else plot_d/2
            dist = (x + w/2 - hx)**2 + (y + d/2 - hy)**2
            
            if strategy == 'baseline':
                candidates.append(((0, 0, 0, dist), c))
            else:
                is_disconnected = 0 if connected else 1
                topological_penalty = 0
                
                if r_type.startswith('pooja') and any(pr['type'].startswith('kitchen') for pr in placed_rooms if get_shared_edge(c, pr) and max(abs(get_shared_edge(c, pr)['x2'] - get_shared_edge(c, pr)['x1']), abs(get_shared_edge(c, pr)['y2'] - get_shared_edge(c, pr)['y1'])) >= 3.0):
                    topological_penalty -= 200
                    
                if not valid_passage_connection and connected:
                    topological_penalty += 1000
                    
                if v_penalty <= 0 or strategy == 'balanced' or strategy.endswith('_first') or strategy == 'bathroom_avoidance':
                    candidates.append(((is_disconnected, topological_penalty + v_penalty, v_penalty, dist), c))
                    
    # Sort by: (disconnected flag, combined topo+vastu penalty, vastu penalty, distance)
    candidates.sort(key=lambda item: (item[0][0], item[0][1], item[0][2], item[0][3]))
    
    res = [c[1] for c in candidates[:max_candidates]]
    return res

def check_partial_feasibility(placed_rooms, unplaced_rooms, reqs, plot_w, plot_d):
    placed_area = sum(r['area'] for r in placed_rooms)
    total_req_area = sum(ROOM_DIMENSIONS.get(r, ROOM_DIMENSIONS['bedroom'])['pref_width'] * ROOM_DIMENSIONS.get(r, ROOM_DIMENSIONS['bedroom'])['pref_depth'] * reqs.rooms[r] for r in reqs.rooms)
    if (plot_w * plot_d) - placed_area < (total_req_area - placed_area):
        return False, "area"
        
    # Reachability potential: check if isolated rooms can physically be bridged by unplaced rooms
    # Find all connected components
    non_parking = [r for r in placed_rooms if r['type'] != 'parking']
    if len(non_parking) <= 1:
        return True, "success"
        
    def dist_between(r1, r2):
        # min distance between two rectangles
        dx = max(0, max(r1['x'] - (r2['x']+r2['width']), r2['x'] - (r1['x']+r1['width'])))
        dy = max(0, max(r1['y'] - (r2['y']+r2['depth']), r2['y'] - (r1['y']+r1['depth'])))
        return (dx**2 + dy**2)**0.5
        
    hall = next((r for r in non_parking if r['type'] == 'hall'), non_parking[0])
    
    # Build adjacency graph: rooms are connected if they share >=2ft edge
    def shares_edge(r1, r2, min_edge=3.0):
        # Check if two rooms share a common boundary segment of at least min_edge length
        dx = max(r1['x'], r2['x']) - min(r1['x']+r1['width'], r2['x']+r2['width'])
        dy = max(r1['y'], r2['y']) - min(r1['y']+r1['depth'], r2['y']+r2['depth'])
        # They share an edge if one dimension overlaps and the other is zero
        if abs(dx) <= 0.5 and dy <= -min_edge:
            return True  # vertical shared edge
        if abs(dy) <= 0.5 and dx <= -min_edge:
            return True  # horizontal shared edge
        return False
    
    def can_be_parent(c_room_type, u_room_type):
        c_base = c_room_type.split('_')[0]
        u_base = u_room_type.split('_')[0]
        if c_base in ['hall', 'dining', 'living', 'circulation', 'corridor', 'passage', 'foyer']:
            return True
        if c_base == 'bedroom' and u_base == 'bathroom':
            return True
        if c_base == 'kitchen' and u_base in ['pooja', 'kitchen']:
            return True
        return False
    
    # BFS from hall to see which rooms are reachable
    reachable = {id(hall)}
    queue = [hall]
    while queue:
        current = queue.pop(0)
        for r in non_parking:
            if id(r) not in reachable and shares_edge(current, r):
                if can_be_parent(current['type'], r['type']) or can_be_parent(r['type'], current['type']):
                    reachable.add(id(r))
                    queue.append(r)
    
    # Any room not reachable from Hall makes this branch a dead-end
    for r in non_parking:
        if id(r) not in reachable:
            return False, "topology"
            
    return True, "success"


def build_floorplan(placed_rooms, reqs, plot_w, plot_d, facing):
    from shapely.geometry import box
    from shapely.ops import unary_union
    polygons = [box(r['x'], r['y'], r['x'] + r['width'], r['y'] + r['depth']) for r in placed_rooms if r['type'] != 'parking']
    built_area = unary_union(polygons).area if polygons else 0.0
    plot_area = plot_w * plot_d
    entrance = create_main_entrance(plot_w, plot_d, facing, placed_rooms)
    vehicle_gate = create_vehicle_gate(plot_w, plot_d, facing, placed_rooms)
    doors = generate_internal_doors(placed_rooms)
    rooms_models = [Room(**r) for r in placed_rooms]
    return FloorPlan(
        plot_width=plot_w, plot_depth=plot_d, plot_area=plot_area, built_area=built_area,
        utilization_percentage=(built_area / plot_area) * 100 if plot_area > 0 else 0,
        facing=facing, rooms=rooms_models, doors=doors,
        entrance=entrance, vehicle_gate=vehicle_gate
    )

def validate_root_topology(root_rooms: list, plot_w: float, plot_d: float, facing: str) -> bool:
    """
    Validates that a root candidate (Parking + Hall) satisfies all hard boundary
    and frontage constraints before entering expensive room beam search.
    """
    hall = next((r for r in root_rooms if r['type'] == 'hall'), None)
    if not hall:
        return False
        
    parking = next((r for r in root_rooms if r['type'] == 'parking'), None)
    
    # 1. Check within plot
    for r in [hall, parking]:
        if not r:
            continue
        if r['x'] < -0.01 or r['y'] < -0.01:
            return False
        if r['x'] + r['width'] > plot_w + 0.01 or r['y'] + r['depth'] > plot_d + 0.01:
            return False
            
    # 2. Check no overlap between Hall and Parking
    if parking and boxes_intersect(hall, parking):
        return False
        
    # 3. Check dimensions
    if hall['width'] < 10.0 or hall['depth'] < 12.0:
        return False
    if parking and (parking['width'] < 9.0 or parking['depth'] < 16.0):
        return False
        
    # 4. Check Hall has valid exterior frontage on requested facing
    if not is_room_on_boundary(hall, facing, plot_w, plot_d):
        return False
    if parking and not is_room_on_boundary(parking, facing, plot_w, plot_d):
        return False
        
    # 5. Check entrance and vehicle gate destinations
    entrance = create_main_entrance(plot_w, plot_d, facing, root_rooms)
    if not entrance or entrance.room != hall['id']:
        return False
        
    if parking:
        gate = create_vehicle_gate(plot_w, plot_d, facing, root_rooms)
        if not gate or gate.room != parking['id']:
            return False
            
    return True


def generate_root_candidates(reqs: FloorPlanRequirements) -> list[tuple[str, list[dict]]]:
    """
    Generates deterministic root candidate topologies:
    Root A: Existing baseline parking/hall arrangement
    Root B: Alternate parking-side / frontage configuration (if parking requested and distinct)
    """
    plot_w = reqs.plot.width
    plot_d = reqs.plot.depth
    facing = reqs.plot.facing.lower()
    
    roots = []
    
    # Root A: Baseline
    base_plan = generate_layout(reqs, seed=42, strategy='baseline', root_variant='A', is_root_generation=True)
    initial_a = [r.model_dump() for r in base_plan.rooms if r.type in ['parking', 'hall']]
    for r in initial_a:
        r['area'] = r['width'] * r['depth']
        
    if validate_root_topology(initial_a, plot_w, plot_d, facing):
        roots.append(('Root_A', initial_a))
        
    # Root B: Alternate parking-side / frontage configuration
    has_parking = reqs.parking or reqs.rooms.get('parking', 0) > 0
    if has_parking:
        plan_b = generate_layout(reqs, seed=42, strategy='baseline', root_variant='B', is_root_generation=True)
        initial_b = [r.model_dump() for r in plan_b.rooms if r.type in ['parking', 'hall']]
        for r in initial_b:
            r['area'] = r['width'] * r['depth']
            
        is_distinct = False
        if initial_a and initial_b:
            p_a = next((r for r in initial_a if r['type'] == 'parking'), None)
            p_b = next((r for r in initial_b if r['type'] == 'parking'), None)
            if p_a and p_b and (abs(p_a['x'] - p_b['x']) > 1.0 or abs(p_a['y'] - p_b['y']) > 1.0):
                is_distinct = True
                
        if is_distinct and validate_root_topology(initial_b, plot_w, plot_d, facing):
            roots.append(('Root_B', initial_b))
            
    return roots


def generate_circulation_candidates(
    initial_rooms: list,
    reqs: FloorPlanRequirements,
    plot_w: float,
    plot_d: float,
    facing: str
) -> list[dict]:
    """
    Deterministically generates candidate circulation entities (e.g. short circulation spine)
    attached directly to Hall's interior edge when direct Hall boundary is insufficient.
    """
    hall = next((r for r in initial_rooms if r['type'] == 'hall'), None)
    if not hall:
        return []
        
    parking = next((r for r in initial_rooms if r['type'] == 'parking'), None)
    
    facing_norm = normalize_orientation(facing)
    axis, _, _, target_val = get_boundary_coordinate(facing_norm, plot_w, plot_d)
    
    # Minimum clear passage width >= 3.5 ft, standardized to 4.0 ft
    circ_w = 4.0
    
    # Depth/length derived from plot depth and branch span:
    if axis == 'y':
        circ_d = max(8.0, min(14.0, round((plot_d * 0.25) / 2) * 2))
    else:
        circ_d = max(8.0, min(14.0, round((plot_w * 0.25) / 2) * 2))
        
    candidates = []
    hx, hy = hall['x'], hall['y']
    hw, hd = hall['width'], hall['depth']
    
    if facing_norm == 'south':
        # Hall is at South (road at y = plot_d). Interior edge is North (y = hy).
        cy = hy - circ_d
        x_positions = []
        if parking and parking['x'] < hx:
            x_positions.append(parking['x'] + parking['width'])
            x_positions.append(hx)
        elif parking and parking['x'] > hx:
            x_positions.append(hx + hw - circ_w)
            x_positions.append(parking['x'] - circ_w)
        else:
            x_positions.append(hx)
            x_positions.append(hx + (hw - circ_w) / 2)
            x_positions.append(hx + hw - circ_w)
            
        for cx in x_positions:
            c = {'x': float(cx), 'y': float(cy), 'width': float(circ_w), 'depth': float(circ_d)}
            if c['x'] < -0.01 or c['y'] < -0.01 or c['x'] + c['width'] > plot_w + 0.01 or c['y'] + c['depth'] > plot_d + 0.01:
                continue
            if any(boxes_intersect(c, r) for r in initial_rooms):
                continue
            edge = get_shared_edge(c, hall)
            if edge and max(abs(edge['x2'] - edge['x1']), abs(edge['y2'] - edge['y1'])) >= 3.0:
                c['area'] = c['width'] * c['depth']
                c['id'] = 'circulation_1'
                c['type'] = 'circulation'
                c['name'] = 'Circulation'
                candidates.append(c)
                
    elif facing_norm == 'north':
        # Hall is at North (road at y = 0). Interior edge is South (y = hy + hd).
        cy = hy + hd
        x_positions = [hx, hx + (hw - circ_w) / 2, hx + hw - circ_w]
        if parking and parking['x'] < hx:
            x_positions.insert(0, parking['x'] + parking['width'])
        for cx in x_positions:
            c = {'x': float(cx), 'y': float(cy), 'width': float(circ_w), 'depth': float(circ_d)}
            if c['x'] < -0.01 or c['y'] < -0.01 or c['x'] + c['width'] > plot_w + 0.01 or c['y'] + c['depth'] > plot_d + 0.01:
                continue
            if any(boxes_intersect(c, r) for r in initial_rooms):
                continue
            edge = get_shared_edge(c, hall)
            if edge and max(abs(edge['x2'] - edge['x1']), abs(edge['y2'] - edge['y1'])) >= 3.0:
                c['area'] = c['width'] * c['depth']
                c['id'] = 'circulation_1'
                c['type'] = 'circulation'
                c['name'] = 'Circulation'
                candidates.append(c)

    elif facing_norm == 'east':
        # Hall is at East (road at x = plot_w). Interior edge is West (x = hx).
        cx = hx - circ_d
        y_positions = [hy, hy + (hd - circ_w) / 2, hy + hd - circ_w]
        for cy in y_positions:
            c = {'x': float(cx), 'y': float(cy), 'width': float(circ_d), 'depth': float(circ_w)}
            if c['x'] < -0.01 or c['y'] < -0.01 or c['x'] + c['width'] > plot_w + 0.01 or c['y'] + c['depth'] > plot_d + 0.01:
                continue
            if any(boxes_intersect(c, r) for r in initial_rooms):
                continue
            edge = get_shared_edge(c, hall)
            if edge and max(abs(edge['x2'] - edge['x1']), abs(edge['y2'] - edge['y1'])) >= 3.0:
                c['area'] = c['width'] * c['depth']
                c['id'] = 'circulation_1'
                c['type'] = 'circulation'
                c['name'] = 'Circulation'
                candidates.append(c)

    elif facing_norm == 'west':
        # Hall is at West (road at x = 0). Interior edge is East (x = hx + hw).
        cx = hx + hw
        y_positions = [hy, hy + (hd - circ_w) / 2, hy + hd - circ_w]
        for cy in y_positions:
            c = {'x': float(cx), 'y': float(cy), 'width': float(circ_d), 'depth': float(circ_w)}
            if c['x'] < -0.01 or c['y'] < -0.01 or c['x'] + c['width'] > plot_w + 0.01 or c['y'] + c['depth'] > plot_d + 0.01:
                continue
            if any(boxes_intersect(c, r) for r in initial_rooms):
                continue
            edge = get_shared_edge(c, hall)
            if edge and max(abs(edge['x2'] - edge['x1']), abs(edge['y2'] - edge['y1'])) >= 3.0:
                c['area'] = c['width'] * c['depth']
                c['id'] = 'circulation_1'
                c['type'] = 'circulation'
                c['name'] = 'Circulation'
                candidates.append(c)

    unique_cands = []
    seen = set()
    for c in candidates:
        key = (round(c['x'], 2), round(c['y'], 2), round(c['width'], 2), round(c['depth'], 2))
        if key not in seen:
            seen.add(key)
            unique_cands.append(c)
    return unique_cands


def _run_beam_search_on_root(
    initial_rooms: list,
    other_rooms: list,
    reqs: FloorPlanRequirements,
    plot_w: float,
    plot_d: float,
    facing: str,
    strategy: str,
    beam_width: int,
    max_candidates_per_room: int,
    metrics: dict
) -> tuple[list[FloorPlan], dict]:
    states = [{'rooms': initial_rooms, 'score': (0, 0, 0, 0)}]
    unplaced_rooms = other_rooms.copy()
    
    for room in other_rooms:
        unplaced_rooms.remove(room)
        next_states = []
        for state in states:
            placed_rooms = state['rooms']
            cands = generate_room_candidates(room, placed_rooms, reqs, plot_w, plot_d, facing, strategy, max_candidates_per_room, metrics["room_candidate_diagnostics"])
            metrics["search_nodes"] += len(cands)
            
            for c in cands:
                new_room = {
                    'id': room['id'], 'type': room['type'], 'name': room['name'],
                    'x': c['x'], 'y': c['y'], 'width': c['width'], 'depth': c['depth'], 'area': c['width'] * c['depth']
                }
                new_rooms = placed_rooms + [new_room]
                
                is_feasible, reason = check_partial_feasibility(new_rooms, unplaced_rooms, reqs, plot_w, plot_d)
                if not is_feasible:
                    metrics["branches_pruned"] += 1
                    if reason == "topology":
                        metrics["topology_pruned"] = metrics.get("topology_pruned", 0) + 1
                    continue
                    
                metrics["partial_candidates"] += 1
                    
                v_pen = get_vastu_penalty(c['x'], c['y'], c['width'], c['depth'], room['type'], plot_w, plot_d, facing)
                
                # Check soft connectivity and topological penalty
                connected = False
                connected_to_hall = False
                connected_to_circ = False
                valid_passage_connection = False
                
                hall_r = next((r for r in placed_rooms if r['type'] == 'hall'), None)
                circ_r = next((r for r in placed_rooms if r['type'] == 'circulation'), None)
                if hall_r:
                    edge = get_shared_edge(new_room, hall_r)
                    if edge and max(abs(edge['x2'] - edge['x1']), abs(edge['y2'] - edge['y1'])) >= 3.0:
                        connected = True
                        connected_to_hall = True
                        valid_passage_connection = True
                        
                if circ_r:
                    edge = get_shared_edge(new_room, circ_r)
                    if edge and max(abs(edge['x2'] - edge['x1']), abs(edge['y2'] - edge['y1'])) >= 3.0:
                        connected = True
                        connected_to_circ = True
                        valid_passage_connection = True
                        
                for pr in placed_rooms:
                    if pr['type'] == 'parking': continue
                    edge = get_shared_edge(new_room, pr)
                    if edge and max(abs(edge['x2'] - edge['x1']), abs(edge['y2'] - edge['y1'])) >= 3.0:
                        connected = True
                        pr_base = pr['type'].split('_')[0]
                        if pr_base in ['hall', 'dining', 'living', 'circulation']:
                            valid_passage_connection = True
                        elif pr_base == 'bedroom' and room['type'].startswith('bathroom'):
                            valid_passage_connection = True
                        elif pr_base == 'kitchen' and (room['type'].startswith('pooja') or room['type'].startswith('kitchen')):
                            valid_passage_connection = True
                            
                # Strict invariant: bedroom must connect to hall or circulation
                if room['type'].startswith('bedroom') and not (connected_to_hall or connected_to_circ):
                    continue
                    
                # Kitchen must connect to hall or circulation (or secondary kitchen)
                if room['type'].startswith('kitchen') and not (connected_to_hall or connected_to_circ):
                    is_sec = any(pr['type'].startswith('kitchen') for pr in placed_rooms 
                                 if get_shared_edge(new_room, pr) and max(abs(get_shared_edge(new_room, pr)['x2'] - get_shared_edge(new_room, pr)['x1']), abs(get_shared_edge(new_room, pr)['y2'] - get_shared_edge(new_room, pr)['y1'])) >= 3.0)
                    if not is_sec:
                        continue
                            
                topo_penalty = 0
                if room['type'].startswith('pooja') and any(pr['type'].startswith('kitchen') for pr in placed_rooms if get_shared_edge(new_room, pr) and max(abs(get_shared_edge(new_room, pr)['x2'] - get_shared_edge(new_room, pr)['x1']), abs(get_shared_edge(new_room, pr)['y2'] - get_shared_edge(new_room, pr)['y1'])) >= 3.0):
                    topo_penalty -= 200
                    
                if connected and not valid_passage_connection:
                    topo_penalty += 1000
                    
                # We also penalize distance slightly to encourage compact packing
                hx = initial_rooms[0]['x'] if initial_rooms else plot_w/2
                hy = initial_rooms[0]['y'] if initial_rooms else plot_d/2
                dist = (c['x'] - hx)**2 + (c['y'] - hy)**2
                dist_penalty = dist / 1000.0
                
                new_score = (state['score'][0] + (0 if connected else 1), 
                             state['score'][1] + topo_penalty + v_pen,
                             state['score'][2] + v_pen, 
                             state['score'][3] + dist_penalty)
                    
                next_states.append({'rooms': new_rooms, 'score': new_score})
                
        if not next_states:
            return [], metrics # Dead branch, no solutions
            
        next_states.sort(key=lambda s: (s['score'][0], s['score'][1], s['score'][2], s['score'][3]))
        if len(next_states) > beam_width:
            metrics["branches_pruned"] += len(next_states) - beam_width
        states = next_states[:beam_width]
        
    metrics["complete_candidates"] = len(states)
    
    final_plans = []
    for s in states:
        rooms_to_build = expand_rooms(s['rooms'], plot_w, plot_d)
        final_plans.append(build_floorplan(rooms_to_build, reqs, plot_w, plot_d, facing))
    return final_plans, metrics


def generate_layout_beam_search(reqs: FloorPlanRequirements, strategy: str = 'balanced', beam_width: int = 15, max_candidates_per_room: int = 6, root_variant: str = None, allow_circulation: bool = True) -> tuple[list[FloorPlan], dict]:
    plot_w, plot_d, facing = reqs.plot.width, reqs.plot.depth, reqs.plot.facing.lower()
    
    metrics = {
        "search_nodes": 0,
        "branches_pruned": 0,
        "partial_candidates": 0,
        "complete_candidates": 0,
        "beam_width": beam_width,
        "max_candidates_per_room": max_candidates_per_room,
        "room_candidate_diagnostics": {},
        "root_candidates_evaluated": 0,
        "root_a_evaluated": False,
        "root_b_evaluated": False,
        "root_a_succeeded": False,
        "root_b_succeeded": False,
        "circulation_evaluated": False,
        "circulation_succeeded": False,
        "selected_root": None,
        "topology_selected": "STAR"
    }
    
    other_rooms = []
    priority = ['bedroom', 'kitchen', 'pooja', 'bathroom', 'dining', 'utility']
    if strategy == 'pooja_first': priority = ['pooja', 'bedroom', 'kitchen', 'bathroom', 'dining', 'utility']
    elif strategy == 'kitchen_first': priority = ['kitchen', 'bedroom', 'pooja', 'bathroom', 'dining', 'utility']
    elif strategy == 'bedroom_first': priority = ['bedroom', 'kitchen', 'pooja', 'bathroom', 'dining', 'utility']
    elif strategy == 'bathroom_avoidance': priority = ['bedroom', 'kitchen', 'bathroom', 'pooja', 'dining', 'utility']
    elif strategy == 'space_first': priority = ['bedroom', 'kitchen', 'dining', 'pooja', 'bathroom', 'utility']
    elif strategy == 'balanced': priority = ['bedroom', 'kitchen', 'pooja', 'bathroom', 'dining', 'utility']
    elif strategy == 'vastu_first': priority = ['bedroom', 'kitchen', 'pooja', 'bathroom', 'dining', 'utility']
    
    for p in priority:
        count = reqs.rooms.get(p, 0)
        norm_type = normalize_room_name(p)
        for i in range(count):
            other_rooms.append({'type': norm_type, 'name': f'{norm_type.capitalize()} {i+1}' if count > 1 else norm_type.capitalize(), 'id': f'{norm_type}_{i+1}'})
    for r_type, count in reqs.rooms.items():
        if r_type == 'hall' or r_type == 'parking' or r_type in priority: continue
        norm_type = normalize_room_name(r_type)
        for i in range(count):
            other_rooms.append({'type': norm_type, 'name': f'{norm_type.capitalize()} {i+1}' if count > 1 else norm_type.capitalize(), 'id': f'{norm_type}_{i+1}'})

    root_candidates = generate_root_candidates(reqs)
    
    if root_variant == 'A':
        root_candidates = [r for r in root_candidates if r[0] == 'Root_A']
    elif root_variant == 'B':
        root_candidates = [r for r in root_candidates if r[0] == 'Root_B']
        
    # Phase 1: Try Star Topology roots
    for root_id, initial_rooms in root_candidates:
        metrics["root_candidates_evaluated"] += 1
        if root_id == 'Root_A':
            metrics["root_a_evaluated"] = True
        elif root_id == 'Root_B':
            metrics["root_b_evaluated"] = True
            
        final_plans, metrics = _run_beam_search_on_root(
            initial_rooms, other_rooms, reqs, plot_w, plot_d, facing, strategy,
            beam_width, max_candidates_per_room, metrics
        )
        
        valid_plans = []
        from layout.validator import validate_layout
        from layout.architecture import validate_final_circulation_invariants
        for p in final_plans:
            val = validate_layout(p)
            circ_val = validate_final_circulation_invariants(p)
            if val.get('valid') and circ_val.get('circulation_valid'):
                valid_plans.append(p)
                
        if valid_plans:
            if root_id == 'Root_A':
                metrics["root_a_succeeded"] = True
            elif root_id == 'Root_B':
                metrics["root_b_succeeded"] = True
            metrics["selected_root"] = root_id
            metrics["topology_selected"] = "STAR"
            return valid_plans, metrics

    # Phase 2: Adaptive Circulation Topology Fallback
    if allow_circulation:
        circ_roots = []
        for root_id, initial_rooms in root_candidates:
            c_cands = generate_circulation_candidates(initial_rooms, reqs, plot_w, plot_d, facing)
            for c_idx, c_room in enumerate(c_cands):
                circ_roots.append((f"{root_id}_Circ_{c_idx+1}", initial_rooms + [c_room]))
                
        for circ_root_id, circ_initial_rooms in circ_roots:
            metrics["root_candidates_evaluated"] += 1
            metrics["circulation_evaluated"] = True
            
            circ_other_rooms = other_rooms.copy()
            circ_priority = ['bedroom', 'kitchen', 'bathroom', 'pooja', 'dining', 'utility']
            circ_other_rooms.sort(key=lambda r: circ_priority.index(r['type']) if r['type'] in circ_priority else 99)
            
            final_plans, metrics = _run_beam_search_on_root(
                circ_initial_rooms, circ_other_rooms, reqs, plot_w, plot_d, facing, strategy,
                beam_width=max(beam_width, 25),
                max_candidates_per_room=max(max_candidates_per_room, 10),
                metrics=metrics
            )
            
            valid_plans = []
            from layout.validator import validate_layout
            from layout.architecture import validate_final_circulation_invariants
            for p in final_plans:
                val = validate_layout(p)
                circ_val = validate_final_circulation_invariants(p)
                if val.get('valid') and circ_val.get('circulation_valid'):
                    valid_plans.append(p)
                    
            if valid_plans:
                metrics["circulation_succeeded"] = True
                metrics["selected_root"] = circ_root_id
                metrics["topology_selected"] = "CIRCULATION_SPINE"
                return valid_plans, metrics
            
    return [], metrics

