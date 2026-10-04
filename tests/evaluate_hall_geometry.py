import sys
import os
import math
from typing import Dict, Any, List, Tuple, Optional

project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_dir not in sys.path:
    sys.path.insert(0, project_dir)

from models.requirements import FloorPlanRequirements, Plot
from models.floorplan import FloorPlan
from config.room_dimensions import ROOM_DIMENSIONS
from layout.orientation import normalize_orientation, get_boundary_coordinate, is_room_on_boundary
from geometry.geometry_utils import boxes_intersect, get_shared_edge
from layout.entrance import create_main_entrance, create_vehicle_gate
from layout.generator import (
    generate_layout,
    generate_room_candidates,
    check_partial_feasibility,
    _run_beam_search_on_root,
    validate_root_topology
)
from layout.validator import validate_layout
from layout.architecture import validate_final_circulation_invariants, validate_circulation_constraints
from utils.normalization import normalize_room_name


def calculate_hall_metrics(
    hall_r: Dict[str, Any],
    parking_r: Optional[Dict[str, Any]],
    plot_w: float,
    plot_d: float,
    facing: str
) -> Dict[str, Any]:
    """
    Computes rigorous boundary and access edge metrics for Hall.
    Distinguishes total perimeter from usable interior access edge.
    """
    hx, hy = hall_r['x'], hall_r['y']
    hw, hd = hall_r['width'], hall_r['depth']
    total_perimeter = 2 * (hw + hd)
    facing_norm = normalize_orientation(facing)

    # 1. Exterior Boundary Edge (Frontage touching road)
    exterior_edge = 0.0
    if facing_norm == 'south' and abs((hy + hd) - plot_d) <= 0.1:
        exterior_edge = hw
    elif facing_norm == 'north' and abs(hy - 0.0) <= 0.1:
        exterior_edge = hw
    elif facing_norm == 'west' and abs(hx - 0.0) <= 0.1:
        exterior_edge = hd
    elif facing_norm == 'east' and abs((hx + hw) - plot_w) <= 0.1:
        exterior_edge = hd

    # 2. Plot Boundary Contact (Edges touching plot walls other than frontage)
    boundary_contact = 0.0
    if abs(hx - 0.0) <= 0.1 and facing_norm != 'west':
        boundary_contact += hd
    if abs((hx + hw) - plot_w) <= 0.1 and facing_norm != 'east':
        boundary_contact += hd
    if abs(hy - 0.0) <= 0.1 and facing_norm != 'north':
        boundary_contact += hw
    if abs((hy + hd) - plot_d) <= 0.1 and facing_norm != 'south':
        boundary_contact += hw

    # 3. Parking Contact Edge (Hall edge blocked by Parking)
    parking_contact = 0.0
    if parking_r:
        edge = get_shared_edge(hall_r, parking_r)
        if edge:
            parking_contact = max(abs(edge['x2'] - edge['x1']), abs(edge['y2'] - edge['y1']))

    # 4. Interior Shared Boundary Length
    # Perimeter minus exterior edge minus non-facing plot boundaries minus parking contact
    interior_edge = max(0.0, total_perimeter - exterior_edge - boundary_contact - parking_contact)

    # 5. Usable Hall-to-Room Access Edge
    # Segments must be contiguous and >= 3.0 ft (minimum door clearance)
    usable_access_edge = 0.0
    # North segment
    if abs(hy - 0.0) > 0.1:
        seg_len = hw
        if parking_r and abs((parking_r['y'] + parking_r['depth']) - hy) <= 0.1:
            overlap = max(0.0, min(hx + hw, parking_r['x'] + parking_r['width']) - max(hx, parking_r['x']))
            seg_len -= overlap
        if seg_len >= 3.0:
            usable_access_edge += seg_len

    # South segment
    if abs((hy + hd) - plot_d) > 0.1:
        seg_len = hw
        if parking_r and abs(parking_r['y'] - (hy + hd)) <= 0.1:
            overlap = max(0.0, min(hx + hw, parking_r['x'] + parking_r['width']) - max(hx, parking_r['x']))
            seg_len -= overlap
        if seg_len >= 3.0:
            usable_access_edge += seg_len

    # West segment
    if abs(hx - 0.0) > 0.1:
        seg_len = hd
        if parking_r and abs((parking_r['x'] + parking_r['width']) - hx) <= 0.1:
            overlap = max(0.0, min(hy + hd, parking_r['y'] + parking_r['depth']) - max(hy, parking_r['y']))
            seg_len -= overlap
        if seg_len >= 3.0:
            usable_access_edge += seg_len

    # East segment
    if abs((hx + hw) - plot_w) > 0.1:
        seg_len = hd
        if parking_r and abs(parking_r['x'] - (hx + hw)) <= 0.1:
            overlap = max(0.0, min(hy + hd, parking_r['y'] + parking_r['depth']) - max(hy, parking_r['y']))
            seg_len -= overlap
        if seg_len >= 3.0:
            usable_access_edge += seg_len

    door_feasible_edge = usable_access_edge
    entrance_feasible = exterior_edge >= 4.0

    return {
        "width": hw,
        "depth": hd,
        "area": hw * hd,
        "aspect_ratio": round(max(hw, hd) / min(hw, hd), 2),
        "total_perimeter": total_perimeter,
        "exterior_edge": exterior_edge,
        "boundary_contact": boundary_contact,
        "parking_contact": parking_contact,
        "interior_edge": interior_edge,
        "usable_access_edge": usable_access_edge,
        "door_feasible_edge": door_feasible_edge,
        "entrance_feasible": entrance_feasible
    }


def evaluate_hall_variant_on_request(
    reqs: FloorPlanRequirements,
    hw: float,
    hd: float,
    root_variant: str = 'A',
    strategy: str = 'balanced'
) -> Dict[str, Any]:
    plot_w = reqs.plot.width
    plot_d = reqs.plot.depth
    facing = reqs.plot.facing.lower()
    has_parking = reqs.parking or reqs.rooms.get('parking', 0) > 0

    axis, _, _, target_val = get_boundary_coordinate(facing, plot_w, plot_d)
    pw, pd = 10.0, 18.0

    # Parking position
    parking_r = None
    if has_parking:
        if root_variant == 'B':
            if axis == 'x':
                px = target_val - pw if target_val > 0 else 0.0
                py = plot_d - pd
            else:
                px = plot_w - pw
                py = target_val - pd if target_val > 0 else 0.0
        else:
            if axis == 'x':
                px = target_val - pw if target_val > 0 else 0.0
                py = 0.0
            else:
                px = 0.0
                py = target_val - pd if target_val > 0 else 0.0
        parking_r = {
            'id': 'parking_1', 'type': 'parking', 'name': 'Parking',
            'x': float(px), 'y': float(py), 'width': float(pw), 'depth': float(pd),
            'area': float(pw * pd)
        }

    # Hall position
    placed_rooms_temp = [parking_r] if parking_r else []
    candidates = []
    if axis == 'x':
        x_options = [target_val - hw if target_val > 0 else 0.0]
        if has_parking:
            if target_val == 0: x_options.append(pw)
            else: x_options.append(plot_w - pw - hw)
        for x in x_options:
            for y in range(0, int(plot_d - hd) + 1, 2):
                c = {'x': float(x), 'y': float(y), 'width': float(hw), 'depth': float(hd)}
                if not any(boxes_intersect(c, pr) for pr in placed_rooms_temp):
                    road_dist = abs(x - target_val) if target_val == 0 else abs(x + hw - target_val)
                    dist = road_dist * 100 + y
                    candidates.append((dist, c))
    else:
        y_options = [target_val - hd if target_val > 0 else 0.0]
        if has_parking:
            if target_val == 0: y_options.append(pd)
            else: y_options.append(plot_d - pd - hd)
        for y in y_options:
            for x in range(0, int(plot_w - hw) + 1, 2):
                c = {'x': float(x), 'y': float(y), 'width': float(hw), 'depth': float(hd)}
                if not any(boxes_intersect(c, pr) for pr in placed_rooms_temp):
                    road_dist = abs(y - target_val) if target_val == 0 else abs(y + hd - target_val)
                    dist = road_dist * 100 + x
                    candidates.append((dist, c))

    if not candidates:
        return {
            "root_valid": False,
            "error": "No valid frontage position found for Hall",
            "hall_metrics": {},
            "complete_candidates": 0,
            "valid_candidates": 0,
            "dominant_failure": "GEOMETRY",
            "evidence": "Hall intersects parking or plot bounds"
        }

    candidates.sort(key=lambda item: item[0])
    best_c = candidates[0][1]
    hall_r = {
        'id': 'hall_1', 'type': 'hall', 'name': 'Hall',
        'x': float(best_c['x']), 'y': float(best_c['y']),
        'width': float(hw), 'depth': float(hd),
        'area': float(hw * hd)
    }

    initial_rooms = [parking_r, hall_r] if parking_r else [hall_r]
    if not validate_root_topology(initial_rooms, plot_w, plot_d, facing):
        return {
            "root_valid": False,
            "error": "Root failed validate_root_topology",
            "hall_metrics": calculate_hall_metrics(hall_r, parking_r, plot_w, plot_d, facing),
            "complete_candidates": 0,
            "valid_candidates": 0,
            "dominant_failure": "ENTRANCE_OR_BOUNDARY",
            "evidence": "Entrance or vehicle gate failed boundary checks"
        }

    hall_m = calculate_hall_metrics(hall_r, parking_r, plot_w, plot_d, facing)

    priority = ['bedroom', 'kitchen', 'pooja', 'bathroom', 'dining', 'utility']
    if strategy == 'kitchen_first': priority = ['kitchen', 'bedroom', 'pooja', 'bathroom']
    elif strategy == 'bedroom_first': priority = ['bedroom', 'kitchen', 'pooja', 'bathroom']
    elif strategy == 'pooja_first': priority = ['pooja', 'bedroom', 'kitchen', 'bathroom']

    other_rooms = []
    for p in priority:
        count = reqs.rooms.get(p, 0)
        norm_type = normalize_room_name(p)
        for i in range(count):
            other_rooms.append({'type': norm_type, 'name': f'{norm_type.capitalize()} {i+1}' if count > 1 else norm_type.capitalize(), 'id': f'{norm_type}_{i+1}'})
    for r_type, count in reqs.rooms.items():
        if r_type in ['hall', 'parking'] or r_type in priority: continue
        norm_type = normalize_room_name(r_type)
        for i in range(count):
            other_rooms.append({'type': norm_type, 'name': f'{norm_type.capitalize()} {i+1}' if count > 1 else norm_type.capitalize(), 'id': f'{norm_type}_{i+1}'})

    metrics = {
        "search_nodes": 0, "branches_pruned": 0, "partial_candidates": 0,
        "complete_candidates": 0, "beam_width": 15, "max_candidates_per_room": 6,
        "room_candidate_diagnostics": {}
    }
    plans, out_metrics = _run_beam_search_on_root(
        initial_rooms, other_rooms.copy(), reqs, plot_w, plot_d, facing,
        strategy, 15, 6, metrics
    )

    valid_count = 0
    circulation_valid_count = 0
    door_feasible_count = 0
    for p in plans:
        val = validate_layout(p)
        circ = validate_final_circulation_invariants(p)
        if circ.get("circulation_valid", False):
            circulation_valid_count += 1
        if val.get("valid", False):
            door_feasible_count += 1
        if val.get("valid", False) and circ.get("circulation_valid", False):
            valid_count += 1

    dominant_failure = "NONE" if valid_count > 0 else "UNKNOWN"
    evidence_str = "Successfully generated valid plan" if valid_count > 0 else ""
    if valid_count == 0:
        if len(plans) == 0:
            states = [{'rooms': initial_rooms, 'score': (0, 0, 0, 0)}]
            unplaced = other_rooms.copy()
            dead_room = None
            dead_reason = None
            for r in other_rooms:
                unplaced.remove(r)
                next_st = []
                cands = []
                for s in states:
                    rc = generate_room_candidates(r, s['rooms'], reqs, plot_w, plot_d, facing, strategy, 10)
                    cands.extend(rc)
                    for c in rc:
                        nr = {'id': r['id'], 'type': r['type'], 'name': r['name'], 'x': c['x'], 'y': c['y'], 'width': c['width'], 'depth': c['depth'], 'area': c['width']*c['depth']}
                        nrooms = s['rooms'] + [nr]
                        is_feas, rsn = check_partial_feasibility(nrooms, unplaced, reqs, plot_w, plot_d)
                        if not is_feas: continue
                        if r['type'].startswith('bedroom'):
                            hr = next(item for item in s['rooms'] if item['type'] == 'hall')
                            edge = get_shared_edge(nr, hr)
                            if not edge or max(abs(edge['x2']-edge['x1']), abs(edge['y2']-edge['y1'])) < 3.0:
                                continue
                        next_st.append({'rooms': nrooms, 'score': (0,0,0,0)})
                states = next_st[:15]
                if not states:
                    dead_room = r['id']
                    if len(cands) == 0:
                        dead_reason = "insufficient_hall_adjacency"
                    else:
                        dead_reason = "partial_feasibility_choke"
                    break
            dominant_failure = "HALL_ACCESS" if dead_reason == "insufficient_hall_adjacency" else "ROOM_CAPACITY"
            evidence_str = f"Deadlock at {dead_room} ({dead_reason}); usable access edge was {hall_m['usable_access_edge']} ft vs needed >= 28 ft"
        else:
            dominant_failure = "CIRCULATION"
            evidence_str = f"{len(plans)} complete candidates failed final hard validation or circulation invariants"

    return {
        "root_valid": True,
        "hall_metrics": hall_m,
        "hall_pos": (hall_r['x'], hall_r['y']),
        "parking_pos": (parking_r['x'], parking_r['y']) if parking_r else None,
        "complete_candidates": len(plans),
        "circulation_valid": circulation_valid_count,
        "door_feasible": door_feasible_count,
        "valid_candidates": valid_count,
        "dominant_failure": dominant_failure,
        "evidence": evidence_str
    }


def run_full_investigation() -> Dict[str, Any]:
    print("=" * 80)
    print("PHASE 4C: CONTROLLED HALL GEOMETRY INVESTIGATION")
    print("=" * 80)

    # 1. Baseline Measurements
    print("\n--- 1. BASELINE BENCHMARK MEASUREMENTS ---")
    baselines = [
        ("Case A (25x40 South)", 25, 40, "south", {"bedroom": 2, "hall": 1, "kitchen": 1, "bathroom": 2, "pooja": 1}, True),
        ("Case B (30x50 South)", 30, 50, "south", {"bedroom": 2, "hall": 1, "kitchen": 1, "bathroom": 2, "pooja": 1}, True),
        ("Case C (25x40 West)",  25, 40, "west",  {"bedroom": 2, "hall": 1, "kitchen": 1, "bathroom": 2, "pooja": 1}, True),
        ("Case D (40x50 East)",  40, 50, "east",  {"bedroom": 2, "hall": 1, "kitchen": 1, "bathroom": 2, "pooja": 1}, True),
        ("TC1 (30x40 West)",     30, 40, "west",  {"bedroom": 2, "hall": 1, "kitchen": 1, "bathroom": 2, "pooja": 1}, True),
        ("TC2 (40x50 East)",     40, 50, "east",  {"bedroom": 3, "hall": 1, "kitchen": 1, "bathroom": 2}, True),
        ("TC3 (30x50 North)",    30, 50, "north", {"bedroom": 2, "hall": 1, "kitchen": 2, "bathroom": 1, "pooja": 1}, True),
        ("TC4 (30x40 West)",     30, 40, "west",  {"bedroom": 1, "hall": 1, "kitchen": 1, "bathroom": 1}, True),
    ]

    baseline_results = []
    for name, w, d, facing, rooms, parking in baselines:
        reqs = FloorPlanRequirements(plot=Plot(width=w, depth=d, facing=facing, unit='ft'), rooms=rooms, parking=parking)
        bp = generate_layout(reqs, seed=42, strategy='baseline')
        hall = next(r for r in bp.rooms if r.type == 'hall')
        pr = next((r for r in bp.rooms if r.type == 'parking'), None)
        hm = calculate_hall_metrics(hall.model_dump(), pr.model_dump() if pr else None, w, d, facing)
        val = validate_layout(bp)
        circ = validate_final_circulation_invariants(bp)
        is_val = val['valid'] and circ['circulation_valid']
        baseline_results.append({
            "name": name, "w": w, "d": d, "facing": facing,
            "hall_w": hall.width, "hall_d": hall.depth, "hall_area": hall.width * hall.depth,
            "total_perimeter": hm['total_perimeter'],
            "exterior_edge": hm['exterior_edge'],
            "interior_edge": hm['interior_edge'],
            "usable_access": hm['usable_access_edge'],
            "valid": is_val
        })
        print(f"{name:<24}: Hall={hall.width}x{hall.depth} (Area={hall.width*hall.depth}) | Ext={hm['exterior_edge']}ft | Int={hm['interior_edge']}ft | Usable={hm['usable_access_edge']}ft | Valid={is_val}")

    # 2. Controlled Hall Geometry Variants for Case A (25x40 South)
    print("\n--- 2. CONTROLLED HALL GEOMETRY EXPERIMENT (25x40 SOUTH) ---")
    reqs_25x40 = FloorPlanRequirements(
        plot=Plot(width=25, depth=40, facing="south", unit="ft"),
        rooms={"bedroom": 2, "hall": 1, "kitchen": 1, "bathroom": 2, "pooja": 1},
        parking=True
    )

    variants = [
        ("Variant 0 (Production Baseline)",  14.0, 16.0, "Current production standard"),
        ("Variant 1 (Inverted Aspect Ratio)", 15.0, 14.0, "Wider, shallower (depth inverted)"),
        ("Variant 2 (Wider + Shallower)",     14.0, 14.0, "Compact square"),
        ("Variant 3 (Narrower + Deeper)",     12.0, 20.0, "Elongated along plot depth"),
        ("Variant 4 (Minimum Width)",         10.0, 20.0, "Narrow corridor-style Hall"),
        ("Variant 5 (Moderately Deeper)",     14.0, 18.0, "Deep Hall with 14ft width"),
        ("Variant 6 (Area-Preserving Aspect)", 12.0, 18.0, "12x18 (Area=216 approx 224)"),
        ("Variant 7 (Max Usable Perimeter)",  10.0, 22.0, "Deep 10x22 Hall claiming max side"),
        ("Variant 7b (Max Area Elongated)",   12.0, 22.0, "Deep 12x22 Hall claiming max side"),
    ]

    variant_results = []
    for var_id, hw, hd, desc in variants:
        for root in ['A', 'B']:
            res = evaluate_hall_variant_on_request(reqs_25x40, hw, hd, root_variant=root, strategy='balanced')
            hm = res['hall_metrics']
            variant_results.append({
                "variant": var_id,
                "desc": desc,
                "root": root,
                "hw": hw, "hd": hd,
                "area": hw * hd,
                "exterior_edge": hm.get('exterior_edge', 0.0),
                "interior_edge": hm.get('interior_edge', 0.0),
                "usable_access": hm.get('usable_access_edge', 0.0),
                "door_feasible": hm.get('door_feasible_edge', 0.0),
                "complete": res['complete_candidates'],
                "valid": res['valid_candidates'],
                "dominant_failure": res['dominant_failure'],
                "evidence": res['evidence']
            })
            print(f"{var_id:<32} Root {root}: Hall={hw}x{hd} | IntEdge={hm.get('interior_edge', 0):<4}ft | Usable={hm.get('usable_access_edge', 0):<4}ft | Complete={res['complete_candidates']} | Valid={res['valid_candidates']} | Failure={res['dominant_failure']}")

    return {
        "baselines": baseline_results,
        "variants": variant_results
    }


if __name__ == "__main__":
    results = run_full_investigation()
