"""
tests/evaluate_circulation_topology.py
PHASE 4D: CIRCULATION & DIRECT-ACCESS TOPOLOGY INVESTIGATION

Controlled analytical harness to evaluate circulation constraints,
direct-access policies, and structural sensitivities on 25x40 South
and control cases WITHOUT modifying production code.
"""

import sys
import os
sys.path.insert(0, os.path.abspath('.'))
import copy
from typing import Dict, Any, List, Tuple
from models.requirements import FloorPlanRequirements, Plot
from models.floorplan import FloorPlan, Room, Door
from layout.generator import (
    generate_layout,
    generate_root_candidates,
    _run_beam_search_on_root,
    generate_room_candidates,
    check_partial_feasibility,
    build_floorplan
)
from layout.validator import validate_layout
from layout.architecture import (
    validate_circulation_constraints,
    validate_final_circulation_invariants,
    evaluate_architecture,
    build_circulation_graph,
    extract_base_type
)
from layout.doors import generate_internal_doors
from geometry.geometry_utils import get_shared_edge, boxes_intersect
from config.architecture_rules import CIRCULATION_CONSTRAINTS, PASSAGE_POLICY
from config.room_dimensions import ROOM_DIMENSIONS
import networkx as nx

def get_standard_cases() -> Dict[str, FloorPlanRequirements]:
    return {
        "Case A (25x40 South)": FloorPlanRequirements(
            plot=Plot(width=25.0, depth=40.0, unit="ft", facing="south"),
            rooms={"bedroom": 2, "hall": 1, "kitchen": 1, "bathroom": 2, "pooja": 1},
            parking=True
        ),
        "Case B (30x50 South)": FloorPlanRequirements(
            plot=Plot(width=30.0, depth=50.0, unit="ft", facing="south"),
            rooms={"bedroom": 2, "hall": 1, "kitchen": 1, "bathroom": 2, "pooja": 1},
            parking=True
        ),
        "Case C (25x40 West)": FloorPlanRequirements(
            plot=Plot(width=25.0, depth=40.0, unit="ft", facing="west"),
            rooms={"bedroom": 2, "hall": 1, "kitchen": 1, "bathroom": 2, "pooja": 1},
            parking=True
        ),
        "Case D (40x50 East)": FloorPlanRequirements(
            plot=Plot(width=40.0, depth=50.0, unit="ft", facing="east"),
            rooms={"bedroom": 2, "hall": 1, "kitchen": 1, "bathroom": 2, "pooja": 1},
            parking=True
        ),
        "TC1 (30x40 West)": FloorPlanRequirements(
            plot=Plot(width=30.0, depth=40.0, unit="ft", facing="west"),
            rooms={"bedroom": 2, "hall": 1, "kitchen": 1, "bathroom": 2, "pooja": 1},
            parking=True
        ),
        "TC2 (40x50 East)": FloorPlanRequirements(
            plot=Plot(width=40.0, depth=50.0, unit="ft", facing="east"),
            rooms={"bedroom": 3, "hall": 1, "kitchen": 1, "bathroom": 2},
            parking=True
        ),
        "TC3 (30x50 North)": FloorPlanRequirements(
            plot=Plot(width=30.0, depth=50.0, unit="ft", facing="north"),
            rooms={"bedroom": 2, "hall": 1, "kitchen": 2, "bathroom": 1, "pooja": 1},
            parking=True
        ),
        "TC4 (30x40 West)": FloorPlanRequirements(
            plot=Plot(width=30.0, depth=40.0, unit="ft", facing="west"),
            rooms={"bedroom": 1, "hall": 1, "kitchen": 1, "bathroom": 1},
            parking=True
        ),
    }

def trace_beam_search_breakdown(reqs: FloorPlanRequirements, root_name: str, root_rooms: list) -> List[Dict[str, Any]]:
    """
    Step through room placement in beam search exactly to detect the earliest collapse point.
    """
    plot_w = reqs.plot.width
    plot_d = reqs.plot.depth
    facing = reqs.plot.facing.lower()
    
    # Priority rooms
    priority = ['bedroom', 'kitchen', 'bathroom', 'pooja', 'dining', 'utility']
    other_rooms = []
    for p in priority:
        count = reqs.rooms.get(p, 0)
        norm_type = p
        for i in range(count):
            other_rooms.append({
                'type': norm_type,
                'name': f'{norm_type.capitalize()} {i+1}' if count > 1 else norm_type.capitalize(),
                'id': f'{norm_type}_{i+1}'
            })
            
    states = [{'rooms': root_rooms, 'score': (0,0,0,0)}]
    unplaced_rooms = other_rooms.copy()
    trace = []
    
    for room in other_rooms:
        unplaced_rooms.remove(room)
        next_states = []
        cands_total = 0
        diag = {}
        for state in states:
            placed = state['rooms']
            cands = generate_room_candidates(
                room, placed, reqs, plot_w, plot_d, facing,
                strategy='baseline', max_candidates=10, room_diagnostics=diag
            )
            cands_total += len(cands)
            for c in cands:
                new_room = {
                    'id': room['id'], 'type': room['type'], 'name': room['name'],
                    'x': c['x'], 'y': c['y'], 'width': c['width'], 'depth': c['depth'],
                    'area': c['width'] * c['depth']
                }
                new_rooms = placed + [new_room]
                is_feas, reason = check_partial_feasibility(new_rooms, unplaced_rooms, reqs, plot_w, plot_d)
                if is_feas:
                    next_states.append({'rooms': new_rooms, 'score': (0,0,0,0)})
                    
        states = next_states[:10]
        trace.append({
            "room_id": room['id'],
            "candidates_found": cands_total,
            "surviving_states": len(states),
            "diagnostics": diag.get(room['type'], {})
        })
        if len(states) == 0:
            break
            
    return trace

def compute_access_budget(reqs: FloorPlanRequirements, root_rooms: list) -> Dict[str, Any]:
    """
    Compute step-by-step Hall access edge budget for 25x40 South.
    """
    plot_w = reqs.plot.width
    plot_d = reqs.plot.depth
    hall = next(r for r in root_rooms if r['type'] == 'hall')
    parking = next((r for r in root_rooms if r['type'] == 'parking'), None)
    
    hx, hy, hw, hd = hall['x'], hall['y'], hall['width'], hall['depth']
    
    # Exterior edge
    ext_len = 0.0
    if hy == 0: ext_len += hw
    if hy + hd == plot_d: ext_len += hw
    if hx == 0: ext_len += hd
    if hx + hw == plot_w: ext_len += hd
    
    # Parking shared edge
    park_len = 0.0
    if parking:
        edge = get_shared_edge(hall, parking)
        if edge:
            park_len = max(abs(edge['x2'] - edge['x1']), abs(edge['y2'] - edge['y1']))
            
    total_perim = 2 * (hw + hd)
    int_edge = total_perim - ext_len - park_len
    
    # Determine usable segments (must be >= 3.0ft for door and accessible for rooms >= 10ft)
    # For South facing, North edge is interior: length = hw
    # West or East edge above parking
    side_past_parking = 0.0
    if parking:
        if hy == parking['y']:
            if hd > parking['depth']:
                side_past_parking = hd - parking['depth']
                
    return {
        "hall_w": hw,
        "hall_d": hd,
        "hall_area": hw * hd,
        "total_perimeter": total_perim,
        "exterior_edge": ext_len,
        "parking_shared_edge": park_len,
        "interior_edge": int_edge,
        "north_edge": hw,
        "side_past_parking": side_past_parking,
        "usable_edge_min_door": hw + (side_past_parking if side_past_parking >= 3.0 else 0.0),
        "usable_edge_min_room": hw + (side_past_parking if side_past_parking >= 10.0 else 0.0),
    }

def run_hypothetical_simulation(
    reqs: FloorPlanRequirements,
    policy_name: str,
    allow_bedroom_passage: bool = False,
    allow_kitchen_passage: bool = False,
    allow_bathroom_passage: bool = False,
    allow_bedroom2_parent_bed1: bool = False,
    allow_kitchen_parent_bed: bool = False,
    allow_pooja_parent_bed: bool = False,
    custom_room_priority: list = None
) -> Dict[str, Any]:
    """
    Run a simulation of candidate generation under a hypothetical policy.
    Does NOT modify production files.
    """
    plot_w = reqs.plot.width
    plot_d = reqs.plot.depth
    facing = reqs.plot.facing.lower()
    
    roots = generate_root_candidates(reqs)
    total_candidates = 0
    complete_candidates = []
    
    priority = custom_room_priority or ['bedroom', 'kitchen', 'bathroom', 'pooja', 'dining', 'utility']
    other_rooms = []
    for p in priority:
        count = reqs.rooms.get(p, 0)
        norm_type = p
        for i in range(count):
            other_rooms.append({
                'type': norm_type,
                'name': f'{norm_type.capitalize()} {i+1}' if count > 1 else norm_type.capitalize(),
                'id': f'{norm_type}_{i+1}'
            })
            
    for root_id, root_rooms in roots:
        states = [{'rooms': root_rooms, 'score': (0,0,0,0)}]
        unplaced = other_rooms.copy()
        
        for room in other_rooms:
            unplaced.remove(room)
            next_states = []
            
            for state in states:
                placed = state['rooms']
                hall_r = next((r for r in placed if r['type'] == 'hall'), None)
                r_type = room['type']
                r_id = room['id']
                
                # Determine allowed parents under this policy
                parents = []
                if hall_r: parents.append(hall_r)
                
                if r_type.startswith('bedroom'):
                    if allow_bedroom2_parent_bed1 and r_id != 'bedroom_1':
                        parents += [pr for pr in placed if pr['type'].startswith('bedroom')]
                elif r_type.startswith('kitchen'):
                    parents += [pr for pr in placed if pr['type'].startswith('kitchen')]
                    if allow_kitchen_parent_bed:
                        parents += [pr for pr in placed if pr['type'].startswith('bedroom')]
                elif r_type.startswith('pooja'):
                    parents += [pr for pr in placed if pr['type'].startswith('kitchen')]
                    if allow_pooja_parent_bed:
                        parents += [pr for pr in placed if pr['type'].startswith('bedroom')]
                elif r_type.startswith('bathroom'):
                    parents += [pr for pr in placed if pr['type'].startswith('bedroom')]
                    
                # Generate positions adjacent to parents
                w_pref = ROOM_DIMENSIONS.get(r_type, ROOM_DIMENSIONS['bedroom'])['pref_width']
                d_pref = ROOM_DIMENSIONS.get(r_type, ROOM_DIMENSIONS['bedroom'])['pref_depth']
                
                # Sizes
                if r_type.startswith('bedroom'):
                    sizes = [(10.0, 14.0), (10.0, 12.0), (14.0, 12.0), (12.0, 14.0), (14.0, 14.0), (12.0, 12.0)]
                elif r_type.startswith('kitchen'):
                    sizes = [(10.0, 10.0), (12.0, 10.0), (10.0, 12.0)]
                elif r_type.startswith('bathroom'):
                    sizes = [(6.0, 8.0), (8.0, 6.0), (6.0, 6.0), (8.0, 8.0)]
                elif r_type.startswith('pooja'):
                    sizes = [(6.0, 6.0), (6.0, 8.0), (8.0, 6.0), (4.0, 6.0)]
                else:
                    sizes = [(w_pref, d_pref)]
                    
                cands_for_state = []
                for w, d in sizes:
                    # Adjacent candidate positions
                    pos_set = set()
                    for p in parents:
                        px, py, pw, pd = float(p['x']), float(p['y']), float(p['width']), float(p['depth'])
                        # North
                        y = py - d
                        if y >= 0:
                            x_min = max(0, int(px - w + 3.0))
                            x_max = min(int(plot_w - w), int(px + pw - 3.0))
                            for step_x in range(x_min, x_max + 1, 2): pos_set.add((float(step_x), float(y)))
                        # South
                        y = py + pd
                        if y <= plot_d - d:
                            x_min = max(0, int(px - w + 3.0))
                            x_max = min(int(plot_w - w), int(px + pw - 3.0))
                            for step_x in range(x_min, x_max + 1, 2): pos_set.add((float(step_x), float(y)))
                        # West
                        x = px - w
                        if x >= 0:
                            y_min = max(0, int(py - d + 3.0))
                            y_max = min(int(plot_d - d), int(py + pd - 3.0))
                            for step_y in range(y_min, y_max + 1, 2): pos_set.add((float(x), float(step_y)))
                        # East
                        x = px + pw
                        if x <= plot_w - w:
                            y_min = max(0, int(py - d + 3.0))
                            y_max = min(int(plot_d - d), int(py + pd - 3.0))
                            for step_y in range(y_min, y_max + 1, 2): pos_set.add((float(x), float(step_y)))
                            
                    for x, y in pos_set:
                        c = {'x': x, 'y': y, 'width': w, 'depth': d}
                        if any(boxes_intersect(c, pr) for pr in placed):
                            continue
                        # Verify edge with at least one parent >= 3.0ft
                        valid_edge = False
                        for p in parents:
                            edge = get_shared_edge(c, p)
                            if edge and max(abs(edge['x2'] - edge['x1']), abs(edge['y2'] - edge['y1'])) >= 3.0:
                                valid_edge = True
                                break
                        if valid_edge:
                            cands_for_state.append(c)
                            
                for c in cands_for_state[:10]:
                    new_room = {
                        'id': room['id'], 'type': room['type'], 'name': room['name'],
                        'x': c['x'], 'y': c['y'], 'width': c['width'], 'depth': c['depth'],
                        'area': c['width'] * c['depth']
                    }
                    next_states.append({'rooms': placed + [new_room], 'score': (0,0,0,0)})
                    
            states = next_states[:15]
            if not states:
                print(f"    [{policy_name}] Collapsed at room: {room['id']}")
                break
                
        for s in states:
            if len(s['rooms']) == len(root_rooms) + len(other_rooms):
                complete_candidates.append(s['rooms'])
                
    # Now evaluate complete candidates against real validators
    door_feasible_count = 0
    circulation_valid_count = 0
    final_valid_count = 0
    entrance_valid_count = 0
    
    first_valid_plan = None
    first_valid_report = None
    
    for r_list in complete_candidates:
        plan = build_floorplan(r_list, reqs, plot_w, plot_d, facing)
        val = validate_layout(plan)
        circ = validate_final_circulation_invariants(plan)
        
        # Check door count: all non-parking rooms must have a door
        non_parking = [r for r in plan.rooms if r.type != 'parking']
        has_doors = len(plan.doors) >= len(non_parking) - 1
        if has_doors:
            door_feasible_count += 1
            
        if val['valid'] and plan.entrance and plan.entrance.room == 'hall_1':
            entrance_valid_count += 1
            
        if circ['circulation_valid']:
            circulation_valid_count += 1
            
        if val['valid'] and circ['circulation_valid']:
            final_valid_count += 1
            if not first_valid_plan:
                first_valid_plan = plan
                first_valid_report = {"val": val, "circ": circ}
                
    return {
        "policy": policy_name,
        "complete_candidates": len(complete_candidates),
        "door_feasible": door_feasible_count,
        "circulation_valid": circulation_valid_count,
        "entrance_valid": entrance_valid_count,
        "final_valid": final_valid_count,
        "sample_valid": first_valid_plan is not None
    }

def evaluate_room_removal_sensitivity(reqs_base: FloorPlanRequirements) -> List[Dict[str, Any]]:
    """
    Remove one requirement at a time to determine structural sensitivity.
    """
    variations = [
        ("Base (25x40 South)", reqs_base),
        ("Remove Pooja", FloorPlanRequirements(
            plot=reqs_base.plot,
            rooms={"bedroom": 2, "hall": 1, "kitchen": 1, "bathroom": 2},
            parking=True
        )),
        ("Remove Bathroom 2", FloorPlanRequirements(
            plot=reqs_base.plot,
            rooms={"bedroom": 2, "hall": 1, "kitchen": 1, "bathroom": 1, "pooja": 1},
            parking=True
        )),
        ("Remove Kitchen", FloorPlanRequirements(
            plot=reqs_base.plot,
            rooms={"bedroom": 2, "hall": 1, "bathroom": 2, "pooja": 1},
            parking=True
        )),
        ("Reduce Bedroom (2->1)", FloorPlanRequirements(
            plot=reqs_base.plot,
            rooms={"bedroom": 1, "hall": 1, "kitchen": 1, "bathroom": 2, "pooja": 1},
            parking=True
        )),
        ("Remove Parking", FloorPlanRequirements(
            plot=reqs_base.plot,
            rooms={"bedroom": 2, "hall": 1, "kitchen": 1, "bathroom": 2, "pooja": 1},
            parking=False
        )),
        ("Remove Pooja + Bath 2", FloorPlanRequirements(
            plot=reqs_base.plot,
            rooms={"bedroom": 2, "hall": 1, "kitchen": 1, "bathroom": 1},
            parking=True
        )),
        ("TC4-style (1 Bed, 1 Kit, 1 Bath)", FloorPlanRequirements(
            plot=reqs_base.plot,
            rooms={"bedroom": 1, "hall": 1, "kitchen": 1, "bathroom": 1},
            parking=True
        )),
    ]
    
    results = []
    for label, reqs in variations:
        roots = generate_root_candidates(reqs)
        total_complete = 0
        total_valid = 0
        for root_id, root_rooms in roots:
            trace = trace_beam_search_breakdown(reqs, root_id, root_rooms)
            last_room = trace[-1] if trace else {}
            # If all rooms placed, compute complete
            if len(trace) == sum(reqs.rooms.get(r, 0) for r in reqs.rooms if r != 'hall'):
                if last_room.get('surviving_states', 0) > 0:
                    total_complete += last_room['surviving_states']
                    
        # Also run default pipeline
        plan = generate_layout(reqs, seed=42, strategy='baseline')
        val = validate_layout(plan)
        circ = validate_final_circulation_invariants(plan)
        is_val = val['valid'] and circ['circulation_valid']
        
        results.append({
            "requirement_variation": label,
            "complete_candidates": total_complete,
            "pipeline_valid": is_val,
            "earliest_blocking": trace[-1]['room_id'] if trace and trace[-1]['surviving_states'] == 0 else "None"
        })
    return results

def main():
    print("="*80)
    print("PHASE 4D: CIRCULATION & DIRECT-ACCESS TOPOLOGY INVESTIGATION")
    print("="*80)
    
    cases = get_standard_cases()
    case_a = cases["Case A (25x40 South)"]
    
    # 1. Trace Earliest Blocking Point
    print("\n--- 1. EARLIEST BLOCKING POINT TRACE (25x40 South) ---")
    roots = generate_root_candidates(case_a)
    for root_id, root_rooms in roots:
        print(f"\nRoot: {root_id}")
        trace = trace_beam_search_breakdown(case_a, root_id, root_rooms)
        for step in trace:
            print(f"  Room: {step['room_id']:<12} | Candidates: {step['candidates_found']:<3} | Surviving States: {step['surviving_states']:<3}")
            
    # 2. Access Budget
    print("\n--- 2. HALL ACCESS BUDGET (25x40 South) ---")
    for root_id, root_rooms in roots:
        budget = compute_access_budget(case_a, root_rooms)
        print(f"\nRoot: {root_id}")
        for k, v in budget.items():
            print(f"  {k:<25}: {v}")
            
    # 3. Room Removal Sensitivity
    print("\n--- 3. ROOM REMOVAL SENSITIVITY ANALYSIS ---")
    sens_results = evaluate_room_removal_sensitivity(case_a)
    for res in sens_results:
        print(f"  {res['requirement_variation']:<35} | Complete: {res['complete_candidates']:<3} | Pipeline Valid: {res['pipeline_valid']!s:<5} | Earliest Block: {res['earliest_blocking']}")

    # 4. Controlled Hypothetical Policy Experiments
    print("\n--- 4. CONTROLLED HYPOTHETICAL POLICY EXPERIMENTS (25x40 South) ---")
    policies = [
        ("Policy 0 (Current Baseline)", {}),
        ("Policy 1 (Pooja via Kitchen)", {"allow_pooja_parent_bed": False}), # Already partially allowed
        ("Policy 2 (Bed2 via Bed1 - En Suite Cluster)", {"allow_bedroom2_parent_bed1": True}),
        ("Policy 3 (Kitchen via Bed1)", {"allow_kitchen_parent_bed": True}),
        ("Policy 4 (Kitchen First + Pooja via Kit)", {"custom_room_priority": ['kitchen', 'pooja', 'bedroom', 'bathroom']}),
        ("Policy 5 (Hierarchical Private Cluster: Bed2 via Bed1 + Baths via Beds)", {
            "allow_bedroom2_parent_bed1": True,
            "custom_room_priority": ['bedroom', 'bathroom', 'kitchen', 'pooja']
        }),
    ]
    
    for p_name, p_kwargs in policies:
        res = run_hypothetical_simulation(case_a, p_name, **p_kwargs)
        print(f"  {res['policy']:<40} | Complete: {res['complete_candidates']:<3} | DoorFeas: {res['door_feasible']:<3} | CircValid: {res['circulation_valid']:<3} | FinalValid: {res['final_valid']:<3}")

    # 5. Direct Access Matrix
    print("\n--- 5. DIRECT-ACCESS MATRIX (Production Rules) ---")
    matrix = [
        ("bedroom_1", "YES", "3.0 ft", "3.0 ft", "NO (Privacy violation / INVALID_PASSAGE)"),
        ("bedroom_2", "YES", "3.0 ft", "3.0 ft", "NO (Privacy violation / INVALID_PASSAGE)"),
        ("kitchen_1", "YES", "3.0 ft", "3.0 ft", "NO (Passage to Bed/Bath forbidden)"),
        ("bathroom_1", "NO (Hall or attached to Bedroom 1)", "3.0 ft", "3.0 ft", "NO (Cannot be passage)"),
        ("bathroom_2", "NO (Hall or attached to Bedroom 2)", "3.0 ft", "3.0 ft", "NO (Cannot be passage)"),
        ("pooja_1", "NO (Hall or Kitchen)", "3.0 ft", "3.0 ft", "Soft penalty only"),
        ("parking_1", "NO (Exterior vehicle gate only)", "N/A", "Vehicle Gate (8-10 ft)", "NO (Cannot connect internally)"),
        ("hall_1", "ROOT (Connects to Exterior Entrance)", "3.0 ft", "3.0 ft (Main Entrance)", "YES (Primary circulation hub)")
    ]
    print(f"  {'Room':<12} | {'Direct Hall Req':<34} | {'Min Edge':<8} | {'Door Width':<10} | {'Can Use Other Room as Passage?'}")
    print("  " + "-"*95)
    for r, dhr, me, dw, pass_rule in matrix:
        print(f"  {r:<12} | {dhr:<34} | {me:<8} | {dw:<10} | {pass_rule}")

    # 6. Detailed Parking Sensitivity Comparison
    print("\n--- 6. PARKING SENSITIVITY INVESTIGATION (25x40 South) ---")
    reqs_with_p = case_a
    reqs_no_p = FloorPlanRequirements(
        plot=Plot(width=25.0, depth=40.0, unit="ft", facing="south"),
        rooms={"bedroom": 2, "hall": 1, "kitchen": 1, "bathroom": 2, "pooja": 1},
        parking=False
    )
    
    for label, r_cfg in [("WITH PARKING", reqs_with_p), ("WITHOUT PARKING", reqs_no_p)]:
        print(f"\n  Configuration: {label}")
        rts = generate_root_candidates(r_cfg)
        for rid, rrms in rts:
            b = compute_access_budget(r_cfg, rrms)
            print(f"    Root {rid}: Hall={b['hall_w']}x{b['hall_d']} | Ext={b['exterior_edge']}ft | ParkShared={b['parking_shared_edge']}ft | IntEdge={b['interior_edge']}ft | UsableNorth={b['north_edge']}ft")
            trace = trace_beam_search_breakdown(r_cfg, rid, rrms)
            for step in trace:
                print(f"      Room: {step['room_id']:<12} | Cands: {step['candidates_found']:<3} | Surviving: {step['surviving_states']:<3}")

    print("\n--- 7. VALID CASE COMPARISON (Access Budgets) ---")
    for name in ["Case C (25x40 West)", "Case B (30x50 South)", "Case D (40x50 East)"]:
        reqs = cases[name]
        rts = generate_root_candidates(reqs)
        for rid, rrms in rts:
            b = compute_access_budget(reqs, rrms)
            print(f"  {name:<25} ({rid}): Hall={b['hall_w']}x{b['hall_d']} | IntEdge={b['interior_edge']}ft | North={b['north_edge']}ft | UsableMinRoom={b['usable_edge_min_room']}ft")

if __name__ == '__main__':
    main()
