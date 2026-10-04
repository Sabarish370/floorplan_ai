"""
tests/evaluate_parking_topology.py
PHASE 4E: ADAPTIVE PARKING & FRONTAGE TOPOLOGY INVESTIGATION

Analytical test harness to investigate parking geometry, frontage consumption,
and alternative parking topologies on 25x40 South and control cases
WITHOUT modifying production code.
"""

import sys
import os
sys.path.insert(0, os.path.abspath('.'))

from typing import Dict, Any, List, Tuple
from models.requirements import FloorPlanRequirements, Plot
from models.floorplan import FloorPlan, Room, Door
from layout.generator import (
    generate_layout,
    generate_root_candidates,
    _run_beam_search_on_root,
    generate_room_candidates,
    check_partial_feasibility,
    build_floorplan,
    validate_root_topology
)
from layout.validator import validate_layout
from layout.architecture import (
    validate_circulation_constraints,
    validate_final_circulation_invariants,
    evaluate_architecture,
    extract_base_type
)
from layout.doors import generate_internal_doors
from layout.entrance import create_main_entrance, create_vehicle_gate
from layout.orientation import normalize_orientation, get_boundary_coordinate, is_room_on_boundary
from geometry.geometry_utils import get_shared_edge, boxes_intersect
from config.room_dimensions import ROOM_DIMENSIONS

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

def compute_detailed_topology_metrics(
    reqs: FloorPlanRequirements,
    root_rooms: list
) -> Dict[str, Any]:
    plot_w = reqs.plot.width
    plot_d = reqs.plot.depth
    facing = reqs.plot.facing.lower()
    
    hall = next(r for r in root_rooms if r['type'] == 'hall')
    parking = next((r for r in root_rooms if r['type'] == 'parking'), None)
    
    hw, hd = hall['width'], hall['depth']
    hx, hy = hall['x'], hall['y']
    
    # Exterior edge of Hall
    hall_ext = 0.0
    if abs(hy - 0.0) <= 0.1: hall_ext += hw
    if abs(hy + hd - plot_d) <= 0.1: hall_ext += hw
    if abs(hx - 0.0) <= 0.1: hall_ext += hd
    if abs(hx + hw - plot_w) <= 0.1: hall_ext += hd
    
    # Parking metrics
    pw = parking['width'] if parking else 0.0
    pd = parking['depth'] if parking else 0.0
    px = parking['x'] if parking else 0.0
    py = parking['y'] if parking else 0.0
    
    park_shared = 0.0
    if parking:
        edge = get_shared_edge(hall, parking)
        if edge:
            park_shared = max(abs(edge['x2'] - edge['x1']), abs(edge['y2'] - edge['y1']))
            
    total_perim = 2 * (hw + hd)
    int_edge = total_perim - hall_ext - park_shared
    
    # Facing axis
    facing_norm = normalize_orientation(facing)
    axis, min_val, max_val, target_val = get_boundary_coordinate(facing_norm, plot_w, plot_d)
    
    # Frontage consumed
    if axis == 'y':
        park_frontage = pw if parking and is_room_on_boundary(parking, facing, plot_w, plot_d) else 0.0
        hall_frontage = hw if is_room_on_boundary(hall, facing, plot_w, plot_d) else 0.0
    else:
        park_frontage = pd if parking and is_room_on_boundary(parking, facing, plot_w, plot_d) else 0.0
        hall_frontage = hd if is_room_on_boundary(hall, facing, plot_w, plot_d) else 0.0
        
    # Usable interior edge for rooms (must be >= 10.0ft contiguous)
    # Segments strictly inside plot and not abutting parking
    usable_segments = []
    # North face (y = hy if facing south)
    if hy > 0.1: # if hy is above 0
        pass
    # For south facing, road is y = plot_d. Interior is towards y = 0.
    # Hall north edge is at y = hy
    if hy > 0 and hy < plot_d:
        usable_segments.append(hw)
    # Check side edges not abutting parking or plot boundary
    # East edge
    if hx + hw < plot_w - 0.1:
        usable_segments.append(hd)
    # West edge
    if hx > 0.1:
        if parking and abs(px + pw - hx) <= 0.1:
            # Parking abuts west edge
            if hd > pd:
                usable_segments.append(hd - pd)
        else:
            usable_segments.append(hd)
            
    usable_min_room = sum(s for s in usable_segments if s >= 10.0)
    
    # Gates and entrance
    ent = create_main_entrance(plot_w, plot_d, facing, root_rooms)
    gate = create_vehicle_gate(plot_w, plot_d, facing, root_rooms) if parking else None
    
    return {
        "plot_w": plot_w,
        "plot_d": plot_d,
        "facing": facing,
        "hall_w": hw,
        "hall_d": hd,
        "hall_x": hx,
        "hall_y": hy,
        "hall_area": hw * hd,
        "hall_perim": total_perim,
        "hall_ext": hall_ext,
        "hall_int": int_edge,
        "usable_int_edge": sum(usable_segments),
        "usable_min_room_edge": usable_min_room,
        "park_w": pw,
        "park_d": pd,
        "park_x": px,
        "park_y": py,
        "park_area": pw * pd,
        "park_frontage": park_frontage,
        "hall_frontage": hall_frontage,
        "total_frontage_consumed": park_frontage + hall_frontage,
        "park_shared_edge": park_shared,
        "entrance_valid": ent is not None and ent.room == hall['id'],
        "gate_valid": gate is not None and (parking is None or gate.room == parking['id']),
        "entrance": ent,
        "vehicle_gate": gate
    }

def run_beam_search_simulation(
    reqs: FloorPlanRequirements,
    root_rooms: list,
    strategy: str = 'baseline',
    max_states: int = 15
) -> Dict[str, Any]:
    plot_w = reqs.plot.width
    plot_d = reqs.plot.depth
    facing = reqs.plot.facing.lower()
    
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
            
    states = [{'rooms': root_rooms, 'score': (0, 0, 0, 0)}]
    unplaced_rooms = other_rooms.copy()
    
    step_records = []
    
    for room in other_rooms:
        unplaced_rooms.remove(room)
        next_states = []
        cands_total = 0
        diag = {}
        for state in states:
            placed = state['rooms']
            cands = generate_room_candidates(
                room, placed, reqs, plot_w, plot_d, facing,
                strategy=strategy, max_candidates=10, room_diagnostics=diag
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
                    next_states.append({'rooms': new_rooms, 'score': (0, 0, 0, 0)})
                    
        states = next_states[:max_states]
        step_records.append({
            "room_id": room['id'],
            "candidates_found": cands_total,
            "surviving_states": len(states)
        })
        if not states:
            break
            
    complete_plans = []
    for s in states:
        if len(s['rooms']) == len(root_rooms) + len(other_rooms):
            complete_plans.append(s['rooms'])
            
    # Validation
    final_valid_count = 0
    circ_valid_count = 0
    door_feasible_count = 0
    
    first_valid_plan = None
    first_valid_report = None
    
    for r_list in complete_plans:
        plan = build_floorplan(r_list, reqs, plot_w, plot_d, facing)
        val = validate_layout(plan)
        circ = validate_final_circulation_invariants(plan)
        non_parking = [r for r in plan.rooms if r.type != 'parking']
        has_doors = len(plan.doors) >= len(non_parking) - 1
        if has_doors:
            door_feasible_count += 1
        if circ['circulation_valid']:
            circ_valid_count += 1
        if val['valid'] and circ['circulation_valid']:
            final_valid_count += 1
            if not first_valid_plan:
                first_valid_plan = plan
                first_valid_report = {"val": val, "circ": circ}
                
    return {
        "step_records": step_records,
        "complete_candidates": len(complete_plans),
        "door_feasible": door_feasible_count,
        "circ_valid": circ_valid_count,
        "final_valid": final_valid_count,
        "sample_valid_plan": first_valid_plan,
        "first_valid_report": first_valid_report
    }

def simulate_parking_topologies(reqs: FloorPlanRequirements) -> List[Dict[str, Any]]:
    """
    Simulates Topologies A, B, C, D, E for 25x40 South.
    """
    plot_w = reqs.plot.width
    plot_d = reqs.plot.depth
    facing = reqs.plot.facing.lower()
    
    topologies = []
    
    # ----------------------------------------------------
    # TOPOLOGY A: Current Root A (Control)
    # ----------------------------------------------------
    # In South facing, road is at y = 40.
    # Parking: x=0..10, y=22..40 (w=10, d=18)
    # Hall: x=11..25, y=24..40 (w=14, d=16)
    root_a = [
        {'id': 'parking_1', 'type': 'parking', 'name': 'Parking', 'x': 0.0, 'y': 22.0, 'width': 10.0, 'depth': 18.0, 'area': 180.0},
        {'id': 'hall_1', 'type': 'hall', 'name': 'Hall', 'x': 11.0, 'y': 24.0, 'width': 14.0, 'depth': 16.0, 'area': 224.0}
    ]
    topologies.append(("Topology A (Current Root A - Control)", root_a, "Current production baseline"))

    # ----------------------------------------------------
    # TOPOLOGY B: Current Root B (Control)
    # ----------------------------------------------------
    # Parking: x=15..25, y=22..40 (w=10, d=18)
    # Hall: x=0..14, y=24..40 (w=14, d=16)
    root_b = [
        {'id': 'parking_1', 'type': 'parking', 'name': 'Parking', 'x': 15.0, 'y': 22.0, 'width': 10.0, 'depth': 18.0, 'area': 180.0},
        {'id': 'hall_1', 'type': 'hall', 'name': 'Hall', 'x': 0.0, 'y': 24.0, 'width': 14.0, 'depth': 16.0, 'area': 224.0}
    ]
    topologies.append(("Topology B (Current Root B - Control)", root_b, "Current Phase 4B alternate corner"))

    # ----------------------------------------------------
    # TOPOLOGY C1: Non-Flanking - Minimal Depth Parking (16ft) with Elongated Hall (20ft)
    # ----------------------------------------------------
    # Parking depth reduced to minimum (16ft, min allowable in ROOM_DIMENSIONS)
    # Hall deepened to 20ft (y=20..40), Parking (y=24..40)
    # Exposes 4ft of Hall West wall above parking
    root_c1 = [
        {'id': 'parking_1', 'type': 'parking', 'name': 'Parking', 'x': 0.0, 'y': 24.0, 'width': 10.0, 'depth': 16.0, 'area': 160.0},
        {'id': 'hall_1', 'type': 'hall', 'name': 'Hall', 'x': 11.0, 'y': 20.0, 'width': 14.0, 'depth': 20.0, 'area': 280.0}
    ]
    topologies.append(("Topology C1 (Non-Flanking: Min Depth 16ft, Deep Hall 20ft)", root_c1, "Exposes 4ft of Hall side wall above parking"))

    # ----------------------------------------------------
    # TOPOLOGY C2: Non-Flanking - Minimum Width Parking (9ft) + Depth 16ft
    # ----------------------------------------------------
    # Parking 9x16 (both absolute minimums in ROOM_DIMENSIONS['parking'])
    # Hall 14x20 at x=10..24
    root_c2 = [
        {'id': 'parking_1', 'type': 'parking', 'name': 'Parking', 'x': 0.0, 'y': 24.0, 'width': 9.0, 'depth': 16.0, 'area': 144.0},
        {'id': 'hall_1', 'type': 'hall', 'name': 'Hall', 'x': 10.0, 'y': 20.0, 'width': 14.0, 'depth': 20.0, 'area': 280.0}
    ]
    topologies.append(("Topology C2 (Non-Flanking: Min Width 9ft + Depth 16ft)", root_c2, "Maximizes open interior buffer"))

    # ----------------------------------------------------
    # TOPOLOGY D: Side/Rear Parking Simulation
    # ----------------------------------------------------
    # Parking located along rear (y=0..18, x=0..10)
    # Hall on frontage (y=24..40, x=0..14)
    # Note: Requires check if road access / gate exists on rear
    root_d = [
        {'id': 'parking_1', 'type': 'parking', 'name': 'Parking', 'x': 0.0, 'y': 0.0, 'width': 10.0, 'depth': 18.0, 'area': 180.0},
        {'id': 'hall_1', 'type': 'hall', 'name': 'Hall', 'x': 0.0, 'y': 24.0, 'width': 14.0, 'depth': 16.0, 'area': 224.0}
    ]
    topologies.append(("Topology D (Side/Rear Parking - Analytical)", root_d, "Simulates rear parking; checks road gate validity"))

    # ----------------------------------------------------
    # TOPOLOGY E: Linear / Compact Frontage Parking (8ft frontage - Analytical Sensitivity)
    # ----------------------------------------------------
    # Parking width = 8.0ft (below 9ft min, analytical test)
    # Hall width = 14.0ft, leaves 3ft buffer
    root_e = [
        {'id': 'parking_1', 'type': 'parking', 'name': 'Parking', 'x': 0.0, 'y': 22.0, 'width': 8.0, 'depth': 18.0, 'area': 144.0},
        {'id': 'hall_1', 'type': 'hall', 'name': 'Hall', 'x': 11.0, 'y': 24.0, 'width': 14.0, 'depth': 16.0, 'area': 224.0}
    ]
    topologies.append(("Topology E (Linear/Compact Frontage: 8ft Width)", root_e, "Analytical sensitivity on reduced frontage"))

    results = []
    for name, root_rooms, note in topologies:
        metrics = compute_detailed_topology_metrics(reqs, root_rooms)
        
        # Check root validity under existing production validate_root_topology
        is_root_valid = validate_root_topology(root_rooms, plot_w, plot_d, facing)
        
        # Run beam search
        sim = run_beam_search_simulation(reqs, root_rooms)
        
        # Extract Bed 1 and Bed 2 candidate counts
        bed1_cands = 0
        bed2_cands = 0
        for step in sim['step_records']:
            if step['room_id'] == 'bedroom_1':
                bed1_cands = step['candidates_found']
            elif step['room_id'] == 'bedroom_2':
                bed2_cands = step['candidates_found']
                
        results.append({
            "name": name,
            "root_rooms": root_rooms,
            "note": note,
            "is_root_valid": is_root_valid,
            "metrics": metrics,
            "simulation": sim,
            "bed1_candidates": bed1_cands,
            "bed2_candidates": bed2_cands,
            "complete_candidates": sim['complete_candidates'],
            "final_valid": sim['final_valid']
        })
        
    return results

def run_frontage_sensitivity_sweep(reqs: FloorPlanRequirements) -> List[Dict[str, Any]]:
    """
    Varies parking width from 8ft to 12ft (in 1ft increments) on 25x40 South.
    """
    plot_w = reqs.plot.width
    plot_d = reqs.plot.depth
    facing = reqs.plot.facing.lower()
    
    sweep_results = []
    for pw in [8.0, 9.0, 10.0, 11.0, 12.0]:
        pd = 18.0
        # Place parking at x=0, y=40-pd
        # Hall placed adjacent at x=pw+1, y=40-16 (w=14, d=16)
        # If pw+1+14 > 25, Hall width must fit: hw = min(14.0, plot_w - pw)
        hw = min(14.0, plot_w - pw - 1.0)
        root = [
            {'id': 'parking_1', 'type': 'parking', 'name': 'Parking', 'x': 0.0, 'y': plot_d - pd, 'width': pw, 'depth': pd, 'area': pw * pd},
            {'id': 'hall_1', 'type': 'hall', 'name': 'Hall', 'x': float(plot_w - hw), 'y': float(plot_d - 16.0), 'width': hw, 'depth': 16.0, 'area': hw * 16.0}
        ]
        m = compute_detailed_topology_metrics(reqs, root)
        sim = run_beam_search_simulation(reqs, root)
        
        bed1_cands = next((s['candidates_found'] for s in sim['step_records'] if s['room_id'] == 'bedroom_1'), 0)
        bed2_cands = next((s['candidates_found'] for s in sim['step_records'] if s['room_id'] == 'bedroom_2'), 0)
        
        sweep_results.append({
            "parking_width": pw,
            "hall_width": hw,
            "parking_frontage_pct": round((pw / plot_w) * 100, 1),
            "hall_usable_edge": m['usable_int_edge'],
            "bed1_candidates": bed1_cands,
            "bed2_candidates": bed2_cands,
            "complete_candidates": sim['complete_candidates'],
            "final_valid": sim['final_valid']
        })
    return sweep_results

def evaluate_controls() -> List[Dict[str, Any]]:
    cases = get_standard_cases()
    results = []
    for name, reqs in cases.items():
        if "25x40 South" in name:
            continue
        roots = generate_root_candidates(reqs)
        for rid, rrms in roots:
            m = compute_detailed_topology_metrics(reqs, rrms)
            sim = run_beam_search_simulation(reqs, rrms)
            results.append({
                "case_name": name,
                "root_id": rid,
                "metrics": m,
                "complete_candidates": sim['complete_candidates'],
                "final_valid": sim['final_valid']
            })
    return results

def main():
    print("="*80)
    print("PHASE 4E: ADAPTIVE PARKING & FRONTAGE TOPOLOGY INVESTIGATION")
    print("="*80)
    
    cases = get_standard_cases()
    case_a = cases["Case A (25x40 South)"]
    
    # 1. Topology Simulations on 25x40 South
    print("\n--- 1. PARKING TOPOLOGY SIMULATION (25x40 South) ---")
    topo_results = simulate_parking_topologies(case_a)
    
    header = f"{'Topology':<38} | {'ParkW':<5} | {'HallW':<5} | {'SharedEdge':<10} | {'UsableEdge':<10} | {'Bed1':<5} | {'Bed2':<5} | {'Complete':<8} | {'Valid':<5} | {'RootValid':<9}"
    print(header)
    print("-" * len(header))
    for t in topo_results:
        m = t['metrics']
        print(f"{t['name'][:38]:<38} | {m['park_w']:<5.1f} | {m['hall_w']:<5.1f} | {m['park_shared_edge']:<10.1f} | {m['usable_int_edge']:<10.1f} | {t['bed1_candidates']:<5} | {t['bed2_candidates']:<5} | {t['complete_candidates']:<8} | {t['final_valid']:<5} | {str(t['is_root_valid']):<9}")
        print(f"    Step progression:")
        for s in t['simulation']['step_records']:
            print(f"      {s['room_id']:<12}: cands={s['candidates_found']}, surviving_states={s['surviving_states']}")
        
    # 2. Frontage Sensitivity Sweep
    print("\n--- 2. FRONTAGE SENSITIVITY SWEEP (25x40 South) ---")
    sweep = run_frontage_sensitivity_sweep(case_a)
    print(f"{'Park Width':<12} | {'Hall Width':<12} | {'Frontage Pct':<14} | {'Usable Edge':<12} | {'Bed1':<6} | {'Bed2':<6} | {'Complete':<8} | {'Valid':<5}")
    print("-" * 85)
    for s in sweep:
        print(f"{s['parking_width']:<12.1f} | {s['hall_width']:<12.1f} | {str(s['parking_frontage_pct'])+'%':<14} | {s['hall_usable_edge']:<12.1f} | {s['bed1_candidates']:<6} | {s['bed2_candidates']:<6} | {s['complete_candidates']:<8} | {s['final_valid']:<5}")
        
    # 3. Control Cases Comparison
    print("\n--- 3. CONTROL CASES COMPARISON ---")
    ctrls = evaluate_controls()
    print(f"{'Case':<25} | {'Root':<8} | {'Plot':<10} | {'Frontage':<8} | {'Hall Size':<10} | {'Usable Edge':<12} | {'Complete':<8} | {'Valid':<5}")
    print("-" * 95)
    for c in ctrls:
        m = c['metrics']
        plot_str = f"{int(m['plot_w'])}x{int(m['plot_d'])}"
        hall_str = f"{int(m['hall_w'])}x{int(m['hall_d'])}"
        print(f"{c['case_name']:<25} | {c['root_id']:<8} | {plot_str:<10} | {m['facing']:<8} | {hall_str:<10} | {m['usable_int_edge']:<12.1f} | {c['complete_candidates']:<8} | {c['final_valid']:<5}")

    # 4. Detailed Entrance and Vehicle Gate Verification for Topologies
    print("\n--- 4. ENTRANCE & VEHICLE GATE VALIDATION (25x40 South) ---")
    for t in topo_results:
        m = t['metrics']
        ent = m['entrance']
        gate = m['vehicle_gate']
        ent_str = f"Side={ent.side}, x={ent.x:.1f}, y={ent.y:.1f}, to={ent.room}" if ent else "None"
        gate_str = f"Side={gate.side}, x={gate.x:.1f}, y={gate.y:.1f}, to={gate.room}" if gate else "None"
        print(f"  {t['name'][:35]}:")
        print(f"    Entrance: {ent_str} (Valid: {m['entrance_valid']})")
        print(f"    Gate    : {gate_str} (Valid: {m['gate_valid']})")

if __name__ == '__main__':
    main()
