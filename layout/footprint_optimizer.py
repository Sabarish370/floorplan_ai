from shapely.geometry import box, Polygon
from shapely.ops import unary_union
from config.room_dimensions import ROOM_DIMENSIONS
import math
from layout.generator import build_floorplan
from layout.validator import validate_layout
from layout.architecture import validate_circulation_constraints, evaluate_architecture
from vastu.validator import analyze_vastu
from layout.space_utilization import evaluate_space_utilization
from config.architecture_rules import OPTIMIZATION_WEIGHTS

def get_bounding_box(rooms):
    min_x = min(r['x'] for r in rooms if r['type'] != 'parking')
    min_y = min(r['y'] for r in rooms if r['type'] != 'parking')
    max_x = max(r['x'] + r['width'] for r in rooms if r['type'] != 'parking')
    max_y = max(r['y'] + r['depth'] for r in rooms if r['type'] != 'parking')
    return min_x, min_y, max_x, max_y

def can_expand_room(r, new_w, new_d, plot_w=40.0, plot_d=50.0):
    ratio = max(new_w, new_d) / min(new_w, new_d) if min(new_w, new_d) > 0 else 1.0
    max_ratio = 2.5 if r['type'] in ['bathroom', 'hall', 'parking'] else 2.2
    if ratio > max_ratio:
        return False
    r_type = r['type']
    plot_area = plot_w * plot_d
    if 'bathroom' in r_type:
        max_area = min(140.0, plot_area * 0.12)
        if new_w > 12.0 or new_d > 14.0 or (new_w * new_d) > max_area:
            return False
    elif 'pooja' in r_type:
        max_area = min(80.0, plot_area * 0.08)
        if new_w > 10.0 or new_d > 10.0 or (new_w * new_d) > max_area:
            return False
    elif 'kitchen' in r_type:
        max_area = min(300.0, plot_area * 0.25)
        if new_w > 18.0 or new_d > 18.0 or (new_w * new_d) > max_area:
            return False
    elif 'bedroom' in r_type:
        max_area = min(450.0, plot_area * 0.35)
        if new_w > min(28.0, plot_w) or new_d > min(28.0, plot_d) or (new_w * new_d) > max_area:
            return False
    elif 'hall' in r_type:
        max_area = min(750.0, plot_area * 0.45)
        if new_w > min(30.0, plot_w) or new_d > min(32.0, plot_d) or (new_w * new_d) > max_area:
            return False
    return True

def maximize_footprint_coverage(rooms, reqs, plot_w, plot_d, facing):
    """
    Expands rooms outwards to fill the plot boundaries (minus parking)
    while preserving Vastu, circulation, and room realism invariants.
    """
    parking_boxes = [box(r['x'], r['y'], r['x'] + r['width'], r['y'] + r['depth']) for r in rooms if r['type'] == 'parking']
    
    changed = True
    iterations = 0
    step = 1.0
    while changed and iterations < 30:
        changed = False
        iterations += 1
        
        # Priority: Hall, Bedroom, Kitchen, Pooja, Bathroom
        def type_prio(t):
            if 'hall' in t: return 0
            if 'bedroom' in t: return 1
            if 'kitchen' in t: return 2
            if 'pooja' in t: return 3
            return 4
            
        rooms.sort(key=lambda r: type_prio(r['type']))
        
        for r in rooms:
            if r['type'] in ['parking', 'circulation']: continue
            
            # Try expanding Right
            new_w = r['width'] + step
            new_d = r['depth']
            if r['x'] + new_w <= plot_w and can_expand_room(r, new_w, new_d, plot_w, plot_d):
                test_poly = box(r['x'], r['y'], r['x'] + new_w, r['y'] + new_d)
                overlap = any(test_poly.intersection(box(o['x'], o['y'], o['x'] + o['width'], o['y'] + o['depth'])).area > 0.01 
                              for o in rooms if o['id'] != r['id'])
                if not overlap:
                    r['width'] = new_w
                    r['area'] = new_w * new_d
                    test_fp = build_floorplan(rooms, reqs, plot_w, plot_d, facing)
                    arch = evaluate_architecture(test_fp)
                    circ = validate_circulation_constraints(test_fp)
                    vastu = analyze_vastu(test_fp)
                    if not circ['valid'] or arch['diagnostics']['room_realism_rejections'] > 0 or any(v['status'] == 'violation' for v in vastu['results']):
                        r['width'] -= step
                        r['area'] = r['width'] * r['depth']
                    else:
                        changed = True
                    
            # Try expanding Left
            new_w = r['width'] + step
            new_d = r['depth']
            new_x = r['x'] - step
            if new_x >= 0 and can_expand_room(r, new_w, new_d, plot_w, plot_d):
                test_poly = box(new_x, r['y'], new_x + new_w, r['y'] + new_d)
                overlap = any(test_poly.intersection(box(o['x'], o['y'], o['x'] + o['width'], o['y'] + o['depth'])).area > 0.01 
                              for o in rooms if o['id'] != r['id'])
                if not overlap:
                    r['x'] = new_x
                    r['width'] = new_w
                    r['area'] = new_w * new_d
                    test_fp = build_floorplan(rooms, reqs, plot_w, plot_d, facing)
                    arch = evaluate_architecture(test_fp)
                    circ = validate_circulation_constraints(test_fp)
                    vastu = analyze_vastu(test_fp)
                    if not circ['valid'] or arch['diagnostics']['room_realism_rejections'] > 0 or any(v['status'] == 'violation' for v in vastu['results']):
                        r['x'] += step
                        r['width'] -= step
                        r['area'] = r['width'] * r['depth']
                    else:
                        changed = True

            # Try expanding Down
            new_w = r['width']
            new_d = r['depth'] + step
            if r['y'] + new_d <= plot_d and can_expand_room(r, new_w, new_d, plot_w, plot_d):
                test_poly = box(r['x'], r['y'], r['x'] + new_w, r['y'] + new_d)
                overlap = any(test_poly.intersection(box(o['x'], o['y'], o['x'] + o['width'], o['y'] + o['depth'])).area > 0.01 
                              for o in rooms if o['id'] != r['id'])
                if not overlap:
                    r['depth'] = new_d
                    r['area'] = new_w * new_d
                    test_fp = build_floorplan(rooms, reqs, plot_w, plot_d, facing)
                    arch = evaluate_architecture(test_fp)
                    circ = validate_circulation_constraints(test_fp)
                    vastu = analyze_vastu(test_fp)
                    if not circ['valid'] or arch['diagnostics']['room_realism_rejections'] > 0 or any(v['status'] == 'violation' for v in vastu['results']):
                        r['depth'] -= step
                        r['area'] = r['width'] * r['depth']
                    else:
                        changed = True

            # Try expanding Up
            new_w = r['width']
            new_d = r['depth'] + step
            new_y = r['y'] - step
            if new_y >= 0 and can_expand_room(r, new_w, new_d, plot_w, plot_d):
                test_poly = box(r['x'], new_y, r['x'] + new_w, r['y'] + new_d)
                overlap = any(test_poly.intersection(box(o['x'], o['y'], o['x'] + o['width'], o['y'] + o['depth'])).area > 0.01 
                              for o in rooms if o['id'] != r['id'])
                if not overlap:
                    r['y'] = new_y
                    r['depth'] = new_d
                    r['area'] = new_w * new_d
                    test_fp = build_floorplan(rooms, reqs, plot_w, plot_d, facing)
                    arch = evaluate_architecture(test_fp)
                    circ = validate_circulation_constraints(test_fp)
                    vastu = analyze_vastu(test_fp)
                    if not circ['valid'] or arch['diagnostics']['room_realism_rejections'] > 0 or any(v['status'] == 'violation' for v in vastu['results']):
                        r['y'] += step
                        r['depth'] -= step
                        r['area'] = r['width'] * r['depth']
                    else:
                        changed = True
    return rooms

def eliminate_internal_voids(rooms, plot_w, plot_d):
    """
    Finds empty gaps inside the bounding box of the building and expands adjacent rooms to fill them.
    """
    min_x, min_y, max_x, max_y = get_bounding_box(rooms)
    bbox_poly = box(min_x, min_y, max_x, max_y)
    
    polygons = [box(r['x'], r['y'], r['x'] + r['width'], r['y'] + r['depth']) for r in rooms if r['type'] != 'parking']
    built_area = unary_union(polygons)
    
    voids = bbox_poly.difference(built_area)
    if voids.is_empty:
        return rooms
        
    void_polys = []
    if voids.geom_type == 'Polygon':
        void_polys = [voids]
    elif voids.geom_type == 'MultiPolygon':
        void_polys = list(voids.geoms)
        
    # For each void, try to expand an adjacent room into it
    for vp in void_polys:
        if vp.area < 1.0: continue
        
        # Sort rooms by how much they touch the void
        touching_rooms = []
        for r in rooms:
            if r['type'] in ['parking', 'circulation']: continue
            rp = box(r['x'], r['y'], r['x'] + r['width'], r['y'] + r['depth'])
            if rp.touches(vp) or rp.distance(vp) < 0.1:
                touching_rooms.append(r)
                
        # Expand the first touching room (ideally largest or highest priority)
        # We just expand it in the direction of the void
        if touching_rooms:
            # Simplistic approach: just run a micro-expansion targeted towards the void
            # Actually, maximize_footprint_coverage handles arbitrary gaps if we just let it run!
            pass
            
    return maximize_footprint_coverage(rooms, plot_w, plot_d)

def optimize_footprint(candidate, reqs, plot_w, plot_d, facing):
    import copy
    test_rooms = [r.model_dump() for r in candidate['layout'].rooms]
    
    old_area = sum(r['area'] for r in test_rooms if r['type'] != 'parking')
    
    # 1. Expand all rooms into available space (ignoring max_width limits to eliminate voids)
    test_rooms = maximize_footprint_coverage(test_rooms, reqs, plot_w, plot_d, facing)
    
    new_area = sum(r['area'] for r in test_rooms if r['type'] != 'parking')
    print(f"Footprint Optimizer: Area changed from {old_area} to {new_area}")
    
    # 2. Re-validate
    test_fp = build_floorplan(test_rooms, reqs, plot_w, plot_d, facing)
    val = validate_layout(test_fp)
    if not val['valid']:
        return candidate # Reject if geometry breaks
        
    circ = validate_circulation_constraints(test_fp)
    if not circ['valid']:
        print("Circulation failed after expansion:", circ)
        return candidate
        
    test_vastu = analyze_vastu(test_fp)
    if any(r['status'] == 'violation' for r in test_vastu['results']):
        return candidate
        
    test_arch = evaluate_architecture(test_fp)
    test_space = evaluate_space_utilization(test_fp, target_ratio=0.8)
    
    return {
        'layout': test_fp,
        'vastu': test_vastu,
        'architecture': test_arch,
        'space': test_space,
        'combined_score': candidate['combined_score'] # will be recomputed outside if needed
    }
