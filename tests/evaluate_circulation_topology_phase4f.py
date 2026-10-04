"""
tests/evaluate_circulation_topology_phase4f.py
PHASE 4F: ADAPTIVE CIRCULATION TOPOLOGY INVESTIGATION

Analytical test harness to investigate explicit circulation topologies
(corridor spine, distribution foyer, bedroom zone, kitchen/pooja sub-zone)
on 25x40 South and control cases WITHOUT modifying production code.
"""

import sys
import os
sys.path.insert(0, os.path.abspath('.'))

from typing import Dict, Any, List, Tuple
from models.requirements import FloorPlanRequirements, Plot
from models.floorplan import FloorPlan, Room, Door, Entrance, VehicleGate
from layout.generator import (
    generate_layout,
    generate_root_candidates,
    check_partial_feasibility,
    build_floorplan,
    validate_root_topology
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
from layout.entrance import create_main_entrance, create_vehicle_gate
from layout.orientation import normalize_orientation, get_boundary_coordinate, is_room_on_boundary
from geometry.geometry_utils import get_shared_edge, boxes_intersect
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

def evaluate_privacy_invariants(floorplan: FloorPlan) -> Dict[str, Any]:
    """
    Rigorously evaluates privacy rules using the circulation graph:
    1. Bedroom is not a passage to another bedroom.
    2. Bedroom is not a passage to kitchen.
    3. Kitchen is not a passage to bedrooms or bathrooms.
    4. Bathrooms are not passages.
    """
    G = build_circulation_graph(floorplan)
    
    bed_passage = []
    kit_passage = []
    bath_passage = []
    
    for node in G.nodes():
        if node in ["exterior", "parking_1"]:
            continue
        node_type = extract_base_type(G.nodes[node].get('type', ''))
        
        # Check articulation / passage role
        H = G.copy()
        H.remove_node(node)
        
        deps = []
        for other in G.nodes():
            if other != node and other != "exterior" and not other.startswith("parking"):
                if nx.has_path(G, "exterior", other) and not nx.has_path(H, "exterior", other):
                    deps.append(other)
                    
        dep_types = [extract_base_type(G.nodes[d].get('type', '')) for d in deps]
        
        if node_type == 'bedroom':
            # Bedroom can only parent its own attached bathroom or balcony/dressing
            invalid = [d for d, dt in zip(deps, dep_types) if dt not in ['bathroom', 'balcony', 'dressing']]
            if invalid:
                bed_passage.append((node, invalid))
        elif node_type == 'kitchen':
            invalid = [d for d, dt in zip(deps, dep_types) if dt in ['bedroom', 'bathroom', 'hall', 'living']]
            if invalid:
                kit_passage.append((node, invalid))
        elif node_type == 'bathroom':
            if deps:
                bath_passage.append((node, deps))
                
    privacy_valid = (len(bed_passage) == 0 and len(kit_passage) == 0 and len(bath_passage) == 0)
    return {
        "privacy_valid": privacy_valid,
        "bed_passage_violations": bed_passage,
        "kit_passage_violations": kit_passage,
        "bath_passage_violations": bath_passage
    }

def run_circulation_simulation_25x40(
    topology_mode: str,
    circulation_config: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Simulates room candidate placement on 25x40 South under a specified circulation topology mode:
    - 'star': Current production star topology (Control)
    - 'spine': Short circulation spine (4x10 to 4x12)
    - 'foyer': Distribution foyer node (6x6)
    - 'bedroom_zone': Private circulation lobby for bedrooms
    - 'compound': Distribution spine + Kitchen directly on Hall + Pooja on Kitchen
    """
    reqs = get_standard_cases()["Case A (25x40 South)"]
    plot_w = 25.0
    plot_d = 40.0
    facing = "south"
    
    # 1. Base Root Setup (Parking + Hall)
    # South road is at y = 40.0
    park_w = circulation_config.get("park_w", 10.0)
    park_d = circulation_config.get("park_d", 16.0)
    hall_w = circulation_config.get("hall_w", 14.0)
    hall_d = circulation_config.get("hall_d", 16.0)
    
    parking_room = {
        'id': 'parking_1', 'type': 'parking', 'name': 'Parking',
        'x': 0.0, 'y': plot_d - park_d, 'width': park_w, 'depth': park_d, 'area': park_w * park_d
    }
    hall_room = {
        'id': 'hall_1', 'type': 'hall', 'name': 'Hall',
        'x': plot_w - hall_w, 'y': plot_d - hall_d, 'width': hall_w, 'depth': hall_d, 'area': hall_w * hall_d
    }
    
    root_rooms = [parking_room, hall_room]
    circ_area = 0.0
    
    # If topology introduces an explicit circulation entity
    if topology_mode in ['spine', 'foyer', 'bedroom_zone', 'compound']:
        cw = circulation_config.get("circ_w", 4.0)
        cd = circulation_config.get("circ_d", 10.0)
        cx = circulation_config.get("circ_x", 11.0)
        cy = circulation_config.get("circ_y", plot_d - hall_d - cd)
        
        circ_room = {
            'id': 'circulation_1', 'type': 'circulation', 'name': 'Circulation',
            'x': cx, 'y': cy, 'width': cw, 'depth': cd, 'area': cw * cd
        }
        root_rooms.append(circ_room)
        circ_area = cw * cd
        
    hall_usable_edge = hall_w # North face
    if hall_d > park_d:
        hall_usable_edge += (hall_d - park_d)
        
    # Determine room order and allowed parenting
    # Under Star: Bed1, Bed2, Kit all require Hall
    # Under Spine/Foyer/Compound:
    # - Kitchen: allowed parent = Hall (or Circ)
    # - Bedrooms: allowed parent = Circulation Node (or Hall if space)
    # - Pooja: allowed parent = Kitchen (or Hall)
    # - Bathrooms: allowed parent = attached to Bedroom, or Circulation Node
    
    priority = ['bedroom_1', 'bedroom_2', 'kitchen_1', 'bathroom_1', 'bathroom_2', 'pooja_1']
    if topology_mode == 'compound':
        priority = ['kitchen_1', 'bedroom_1', 'bedroom_2', 'bathroom_1', 'bathroom_2', 'pooja_1']
        
    states = [{'rooms': root_rooms, 'score': 0}]
    step_records = []
    
    for room_id in priority:
        r_type = room_id.split('_')[0]
        next_states = []
        cands_total = 0
        
        # Dimensions
        if r_type == 'bedroom':
            sizes = [(10.0, 12.0), (12.0, 10.0), (10.0, 10.0), (10.0, 14.0), (11.0, 11.0)]
        elif r_type == 'kitchen':
            sizes = [(10.0, 10.0), (10.0, 8.0), (8.0, 10.0), (9.0, 10.0)]
        elif r_type == 'bathroom':
            sizes = [(5.0, 7.0), (6.0, 6.0), (5.0, 8.0), (6.0, 7.0), (5.0, 6.0)]
        elif r_type == 'pooja':
            sizes = [(4.0, 5.0), (4.0, 6.0), (5.0, 5.0), (4.0, 4.0)]
            
        for state in states:
            placed = state['rooms']
            hall_r = next(r for r in placed if r['type'] == 'hall')
            circ_r = next((r for r in placed if r['type'] == 'circulation'), None)
            
            # Allowed parents based on topology mode
            parents = []
            if topology_mode == 'star':
                if r_type == 'bedroom': parents = [hall_r]
                elif r_type == 'kitchen': parents = [hall_r]
                elif r_type == 'pooja': parents = [hall_r] + [r for r in placed if r['type'] == 'kitchen']
                elif r_type == 'bathroom': parents = [hall_r] + [r for r in placed if r['type'] == 'bedroom']
            elif topology_mode in ['spine', 'foyer', 'compound']:
                if r_type == 'bedroom':
                    parents = [circ_r] if circ_r else [hall_r]
                elif r_type == 'kitchen':
                    parents = [hall_r] + ([circ_r] if circ_r else [])
                elif r_type == 'pooja':
                    parents = [r for r in placed if r['type'] == 'kitchen'] + [hall_r]
                elif r_type == 'bathroom':
                    # Allow attached to bedroom (1:1 per bedroom) or connected to circulation
                    if room_id == 'bathroom_1':
                        parents = [r for r in placed if r['id'] == 'bedroom_1'] + ([circ_r] if circ_r else [])
                    elif room_id == 'bathroom_2':
                        parents = [r for r in placed if r['id'] == 'bedroom_2'] + ([circ_r] if circ_r else [])
                    else:
                        parents = [r for r in placed if r['type'] == 'bedroom'] + ([circ_r] if circ_r else [])
            elif topology_mode == 'bedroom_zone':
                if r_type == 'bedroom': parents = [circ_r] if circ_r else []
                elif r_type == 'kitchen': parents = [hall_r]
                elif r_type == 'pooja': parents = [r for r in placed if r['type'] == 'kitchen']
                elif r_type == 'bathroom':
                    if room_id == 'bathroom_1': parents = [r for r in placed if r['id'] == 'bedroom_1']
                    else: parents = [r for r in placed if r['id'] == 'bedroom_2']
                
            # Scan positions adjacent to parents
            cands_for_state = []
            for w, d in sizes:
                pos_set = set()
                for p in parents:
                    px, py, pw, pd = p['x'], p['y'], p['width'], p['depth']
                    # North of parent
                    y = py - d
                    if y >= 0:
                        x_min = max(0, int(px - w + 3.0))
                        x_max = min(int(plot_w - w), int(px + pw - 3.0))
                        for sx in range(x_min, x_max + 1, 2): pos_set.add((float(sx), float(y)))
                    # South of parent
                    y = py + pd
                    if y <= plot_d - d:
                        x_min = max(0, int(px - w + 3.0))
                        x_max = min(int(plot_w - w), int(px + pw - 3.0))
                        for sx in range(x_min, x_max + 1, 2): pos_set.add((float(sx), float(y)))
                    # West of parent
                    x = px - w
                    if x >= 0:
                        y_min = max(0, int(py - d + 3.0))
                        y_max = min(int(plot_d - d), int(py + pd - 3.0))
                        for sy in range(y_min, y_max + 1, 2): pos_set.add((float(x), float(sy)))
                    # East of parent
                    x = px + pw
                    if x <= plot_w - w:
                        y_min = max(0, int(py - d + 3.0))
                        y_max = min(int(plot_d - d), int(py + pd - 3.0))
                        for sy in range(y_min, y_max + 1, 2): pos_set.add((float(x), float(sy)))
                        
                for x, y in pos_set:
                    c = {'x': x, 'y': y, 'width': w, 'depth': d}
                    if any(boxes_intersect(c, pr) for pr in placed):
                        continue
                    # Check shared edge >= 3.0 with at least one parent
                    valid_edge = False
                    for p in parents:
                        edge = get_shared_edge(c, p)
                        if edge and max(abs(edge['x2'] - edge['x1']), abs(edge['y2'] - edge['y1'])) >= 3.0:
                            valid_edge = True
                            break
                    if valid_edge:
                        cands_for_state.append(c)
                        
            cands_total += len(cands_for_state)
            for c in cands_for_state[:10]:
                new_room = {
                    'id': room_id, 'type': r_type, 'name': room_id.capitalize(),
                    'x': c['x'], 'y': c['y'], 'width': c['width'], 'depth': c['depth'],
                    'area': c['width'] * c['depth']
                }
                next_states.append({'rooms': placed + [new_room], 'score': 0})
                
        states = next_states[:15]
        step_records.append({
            "room_id": room_id,
            "candidates_found": cands_total,
            "surviving_states": len(states)
        })
        if not states:
            break
            
    complete_plans = []
    total_requested_rooms = len(root_rooms) + len(priority)
    for s in states:
        if len(s['rooms']) == total_requested_rooms:
            complete_plans.append(s['rooms'])
            
    # Evaluation of complete plans
    final_valid_count = 0
    privacy_valid_count = 0
    door_feasible_count = 0
    sample_plan = None
    sample_val = None
    sample_privacy = None
    
    for r_list in complete_plans:
        # Build floorplan model
        doors = generate_internal_doors(r_list)
        entrance = create_main_entrance(plot_w, plot_d, facing, r_list)
        gate = create_vehicle_gate(plot_w, plot_d, facing, r_list)
        rooms_models = [Room(**r) for r in r_list]
        built_area = sum(r['area'] for r in r_list if r['type'] != 'parking')
        
        plan = FloorPlan(
            plot_width=plot_w, plot_depth=plot_d, plot_area=plot_w * plot_d,
            built_area=built_area, utilization_percentage=(built_area / 1000.0) * 100,
            facing=facing, rooms=rooms_models, doors=doors,
            entrance=entrance, vehicle_gate=gate
        )
        
        # Validations
        val = validate_layout(plan)
        circ_inv = validate_final_circulation_invariants(plan)
        priv = evaluate_privacy_invariants(plan)
        non_parking = [r for r in plan.rooms if r.type != 'parking']
        has_all_doors = len(doors) >= len(non_parking) - 1
        
        if has_all_doors:
            door_feasible_count += 1
        if priv['privacy_valid']:
            privacy_valid_count += 1
            
        if val['valid'] and circ_inv['circulation_valid'] and priv['privacy_valid'] and has_all_doors:
            final_valid_count += 1
            if not sample_plan:
                sample_plan = plan
                sample_val = val
                sample_privacy = priv
                
    # Direct Hall frontage demand:
    # Under Star: Bed1(10) + Bed2(10) + Kit(10) = 30ft
    # Under Compound: Kit(10) + Circ(4) = 14ft
    hall_demand = 30.0 if topology_mode == 'star' else (10.0 + circulation_config.get("circ_w", 4.0))
    
    return {
        "mode": topology_mode,
        "circulation_area": circ_area,
        "hall_demand": hall_demand,
        "hall_usable_edge": hall_usable_edge,
        "step_records": step_records,
        "complete_candidates": len(complete_plans),
        "door_feasible": door_feasible_count,
        "privacy_valid": privacy_valid_count,
        "final_valid": final_valid_count,
        "sample_plan": sample_plan,
        "sample_val": sample_val,
        "sample_privacy": sample_privacy
    }

def main():
    print("="*80)
    print("PHASE 4F: ADAPTIVE CIRCULATION TOPOLOGY INVESTIGATION")
    print("="*80)
    
    topologies_to_test = [
        ("Topology A (Current Star - Control)", "star", {}),
        ("Topology B (Short Circulation Spine 4x10)", "spine", {
            "park_w": 10.0, "park_d": 16.0, "hall_w": 14.0, "hall_d": 16.0,
            "circ_w": 4.0, "circ_d": 10.0, "circ_x": 10.0, "circ_y": 14.0
        }),
        ("Topology C (Distribution Foyer Node 6x6)", "foyer", {
            "park_w": 10.0, "park_d": 16.0, "hall_w": 14.0, "hall_d": 16.0,
            "circ_w": 6.0, "circ_d": 6.0, "circ_x": 10.0, "circ_y": 18.0
        }),
        ("Topology D (Bedroom Zone 4x8)", "bedroom_zone", {
            "park_w": 10.0, "park_d": 16.0, "hall_w": 14.0, "hall_d": 16.0,
            "circ_w": 4.0, "circ_d": 8.0, "circ_x": 0.0, "circ_y": 16.0
        }),
        ("Topology F (Compound Circulation Architecture)", "compound", {
            "park_w": 10.0, "park_d": 16.0, "hall_w": 14.0, "hall_d": 16.0,
            "circ_w": 4.0, "circ_d": 10.0, "circ_x": 10.0, "circ_y": 14.0
        })
    ]
    
    print("\n--- 1. CIRCULATION TOPOLOGY COMPARISON (25x40 South) ---")
    results = []
    for name, mode, cfg in topologies_to_test:
        res = run_circulation_simulation_25x40(mode, cfg)
        results.append((name, res))
        
        bed1_s = next((s for s in res['step_records'] if s['room_id'] == 'bedroom_1'), {})
        bed2_s = next((s for s in res['step_records'] if s['room_id'] == 'bedroom_2'), {})
        kit_s = next((s for s in res['step_records'] if s['room_id'] == 'kitchen_1'), {})
        
        print(f"\n{name}:")
        print(f"  Circulation Area      : {res['circulation_area']} sq.ft")
        print(f"  Hall Direct Demand    : {res['hall_demand']} ft (Usable Edge: {res['hall_usable_edge']} ft)")
        print(f"  Bedroom 1 Candidates  : {bed1_s.get('candidates_found', 0)} (surviving: {bed1_s.get('surviving_states', 0)})")
        print(f"  Bedroom 2 Candidates  : {bed2_s.get('candidates_found', 0)} (surviving: {bed2_s.get('surviving_states', 0)})")
        print(f"  Kitchen 1 Candidates  : {kit_s.get('candidates_found', 0)} (surviving: {kit_s.get('surviving_states', 0)})")
        print(f"  Complete Candidates   : {res['complete_candidates']}")
        print(f"  Door Feasible Plans   : {res['door_feasible']}")
        print(f"  Privacy Valid Plans   : {res['privacy_valid']}")
        print(f"  Final Valid Plans     : {res['final_valid']}")
        
    print("\n--- 2. REQUIRED COMPARISON TABLE ---")
    header = f"{'Topology':<38} | {'CircArea':<8} | {'HallDemand':<10} | {'UsableEdge':<10} | {'Bed1':<5} | {'Bed2':<5} | {'Kitchen':<7} | {'Complete':<8} | {'FinalValid':<10}"
    print(header)
    print("-" * len(header))
    for name, res in results:
        bed1_s = next((s for s in res['step_records'] if s['room_id'] == 'bedroom_1'), {})
        bed2_s = next((s for s in res['step_records'] if s['room_id'] == 'bedroom_2'), {})
        kit_s = next((s for s in res['step_records'] if s['room_id'] == 'kitchen_1'), {})
        print(f"{name[:38]:<38} | {res['circulation_area']:<8.1f} | {res['hall_demand']:<10.1f} | {res['hall_usable_edge']:<10.1f} | {bed1_s.get('candidates_found', 0):<5} | {bed2_s.get('candidates_found', 0):<5} | {kit_s.get('candidates_found', 0):<7} | {res['complete_candidates']:<8} | {res['final_valid']:<10}")

    print("\n--- 3. SAMPLE VALID PLAN VERIFICATION (Topology F) ---")
    for name, res in results:
        if res['sample_plan']:
            plan = res['sample_plan']
            print(f"  Plan under {name}:")
            print(f"    Built Area: {plan.built_area:.1f} sq.ft, Utilization: {plan.utilization_percentage:.1f}%")
            print(f"    Entrance: Side={plan.entrance.side}, x={plan.entrance.x:.1f}, y={plan.entrance.y:.1f}, to={plan.entrance.room}")
            print(f"    Vehicle Gate: Side={plan.vehicle_gate.side}, x={plan.vehicle_gate.x:.1f}, y={plan.vehicle_gate.y:.1f}, to={plan.vehicle_gate.room}")
            print(f"    Doors Generated ({len(plan.doors)}):")
            for d in plan.doors:
                print(f"      {d.from_room} <---> {d.to_room} (w={d.width:.1f}ft at x={d.x:.1f}, y={d.y:.1f})")
            print(f"    Rooms ({len(plan.rooms)}):")
            for r in plan.rooms:
                print(f"      {r.id:<14} : {r.width}x{r.depth} at ({r.x}, {r.y}) [Area={r.width*r.depth}]")
            break

    print("\n--- 4. CONTROL CASES EVALUATION (Current Production Baseline) ---")
    ctrl_cases = get_standard_cases()
    for c_name, req in ctrl_cases.items():
        if "25x40 South" in c_name:
            continue
        try:
            prod_plan = generate_layout(req)
            if prod_plan:
                val = validate_layout(prod_plan)
                status = "VALID" if val['valid'] else f"INVALID ({val['errors']})"
                print(f"  {c_name:<25}: {status} (Built: {prod_plan.built_area:.1f} sq.ft, Rooms: {len(prod_plan.rooms)})")
            else:
                print(f"  {c_name:<25}: INFEASIBLE_REQUEST (No plan generated)")
        except Exception as e:
            print(f"  {c_name:<25}: EXCEPTION ({e})")

if __name__ == '__main__':
    main()
