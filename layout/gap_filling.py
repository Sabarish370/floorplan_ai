from copy import deepcopy
from layout.generator import build_floorplan
from layout.validator import validate_layout
from layout.architecture import validate_circulation_constraints, evaluate_architecture
from vastu.validator import analyze_vastu
from layout.space_utilization import evaluate_space_utilization
from config.architectural_config import ARCHITECTURAL_CONFIG
from config.room_dimensions import ROOM_DIMENSIONS
import random

def score_candidate(fp, vastu_res, arch_res, space_res):
    return (
        vastu_res['score'] * ARCHITECTURAL_CONFIG['weights']['vastu'] +
        arch_res['architectural_score'] * ARCHITECTURAL_CONFIG['weights']['architecture'] +
        space_res['space_utilization_score'] * ARCHITECTURAL_CONFIG['weights'].get('space', 0.25) +
        space_res['compactness_score'] * ARCHITECTURAL_CONFIG['weights'].get('compactness', 0.10)
    )

def intersect(r1, r2):
    return not (r1['x'] + r1['width'] <= r2['x'] + 0.01 or
                r2['x'] + r2['width'] <= r1['x'] + 0.01 or
                r1['y'] + r1['depth'] <= r2['y'] + 0.01 or
                r2['y'] + r2['depth'] <= r1['y'] + 0.01)

def fill_gaps(candidate, reqs, plot_w, plot_d, facing, max_iterations=50):
    best_layout = candidate['layout']
    best_vastu = candidate['vastu']
    best_space = candidate['space']
    best_arch = evaluate_architecture(best_layout)
    best_score = score_candidate(best_layout, best_vastu, best_arch, best_space)
    
    current_rooms = [r.model_dump() for r in best_layout.rooms]
    
    step = 0.5
    improved = True
    iterations = 0
    
    while improved and iterations < max_iterations:
        improved = False
        iterations += 1
        
        # Priority for moves
        def type_priority(t):
            if 'hall' in t: return 0
            if 'bedroom' in t: return 1
            if 'kitchen' in t: return 2
            if 'pooja' in t: return 3
            if 'bathroom' in t: return 4
            return 5
            
        current_rooms.sort(key=lambda r: type_priority(r['type']))
        
        for i, room in enumerate(current_rooms):
            if room['type'] == 'parking':
                continue
                
            r_type = room['type'].split('_')[0]
            dims = ROOM_DIMENSIONS.get(r_type, ROOM_DIMENSIONS.get('bedroom'))
            max_w = dims.get('max_width', dims['pref_width'] * 1.5)
            max_d = dims.get('max_depth', dims['pref_depth'] * 1.5)
            
            moves = [
                ('move', step, 0), ('move', -step, 0), ('move', 0, step), ('move', 0, -step),
                ('expand', step, 0), ('expand', -step, 0), ('expand', 0, step), ('expand', 0, -step)
            ]
            
            # Shuffle moves for slightly non-deterministic search
            random.shuffle(moves)
            
            for action, dx, dy in moves:
                test_rooms = deepcopy(current_rooms)
                tr = test_rooms[i]
                
                if action == 'move':
                    tr['x'] += dx
                    tr['y'] += dy
                elif action == 'expand':
                    if dx > 0: tr['width'] += dx
                    if dx < 0:
                        tr['x'] += dx
                        tr['width'] -= dx
                    if dy > 0: tr['depth'] += dy
                    if dy < 0:
                        tr['y'] += dy
                        tr['depth'] -= dy
                
                # Fast boundary check
                if tr['x'] < 0 or tr['y'] < 0 or tr['x'] + tr['width'] > plot_w or tr['y'] + tr['depth'] > plot_d:
                    continue
                    
                # Fast dimension check
                if tr['width'] > max_w or tr['depth'] > max_d or tr['width'] < dims['min_width'] or tr['depth'] < dims['min_depth']:
                    continue
                    
                # Fast overlap check
                overlap = False
                for j, other in enumerate(test_rooms):
                    if i != j and intersect(tr, other):
                        overlap = True
                        break
                if overlap:
                    continue
                    
                # Deep validation
                test_fp = build_floorplan(test_rooms, reqs, plot_w, plot_d, facing)
                val = validate_layout(test_fp)
                if not val['valid']:
                    continue
                    
                errs = " ".join(val.get("errors", [])).lower()
                if "connect" in errs or "accessible" in errs:
                    continue
                    
                circ = validate_circulation_constraints(test_fp)
                if not circ['valid']:
                    continue
                    
                test_vastu = analyze_vastu(test_fp)
                if any(r['status'] == 'violation' for r in test_vastu['results']):
                    continue
                    
                test_arch = evaluate_architecture(test_fp)
                test_space = evaluate_space_utilization(test_fp, target_ratio=0.8)
                
                test_score = score_candidate(test_fp, test_vastu, test_arch, test_space)
                
                # Accept if better global score
                if test_score > best_score + 0.1: # tiny margin to prevent loops
                    best_layout = test_fp
                    best_vastu = test_vastu
                    best_arch = test_arch
                    best_space = test_space
                    best_score = test_score
                    current_rooms = test_rooms
                    improved = True
                    break # Break moves loop and move to next room/iteration
                    
    return {
        'layout': best_layout,
        'vastu': best_vastu,
        'architecture': best_arch,
        'space': best_space,
        'combined_score': best_score
    }
