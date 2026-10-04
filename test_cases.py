import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from typing import Dict, Any, List
import networkx as nx

from models.requirements import FloorPlanRequirements, Plot
from models.floorplan import FloorPlan
from layout.generator import generate_layout
from layout.vastu_optimizer import optimize_layout
from layout.validator import validate_layout
from layout.architecture import validate_final_circulation_invariants, build_circulation_graph
from geometry.geometry_utils import get_shared_edge
from vastu import analyze_vastu

test_cases = [
    FloorPlanRequirements(
        plot=Plot(width=30, depth=40, facing="west", unit="ft"),
        rooms={"bedroom": 2, "hall": 1, "kitchen": 1, "bathroom": 2, "pooja": 1},
        parking=True,
        request_id="req11111", test_case_name="TEST CASE 1"
    ),
    FloorPlanRequirements(
        plot=Plot(width=40, depth=50, facing="east", unit="ft"),
        rooms={"bedroom": 3, "hall": 1, "kitchen": 1, "bathroom": 2},
        parking=True,
        request_id="req22222", test_case_name="TEST CASE 2"
    ),
    FloorPlanRequirements(
        plot=Plot(width=30, depth=50, facing="north", unit="ft"),
        rooms={"bedroom": 2, "hall": 1, "kitchen": 2, "bathroom": 1, "pooja": 1},
        parking=True,
        request_id="req33333", test_case_name="TEST CASE 3"
    ),
    FloorPlanRequirements(
        plot=Plot(width=30, depth=40, facing="west", unit="ft"),
        rooms={"bedroom": 1, "hall": 1, "kitchen": 1, "bathroom": 1},
        parking=True,
        request_id="req44444", test_case_name="TEST CASE 4"
    )
]

def evaluate_floorplan_invariants(tc: FloorPlanRequirements, layout: FloorPlan, opt_meta: Dict[str, Any], vastu_result: Any) -> Dict[str, Any]:
    """
    Strict, deterministic verification of hard architectural and geometric invariants.
    Optimization scores are strictly treated as quality metrics and NEVER as validity proof.
    """
    # 1. Geometry Validation
    val = validate_layout(layout)
    errors = val.get("errors", [])
    overlaps = [e for e in errors if "overlap" in e.lower()]
    boundary_violations = [e for e in errors if "outside" in e.lower() or "boundary" in e.lower()]
    invalid_dimensions = [e for e in errors if "dimension" in e.lower()]
    geometry_valid = (val.get("valid", False) and len(overlaps) == 0 and len(boundary_violations) == 0 and len(invalid_dimensions) == 0)

    # 2. Circulation & Invariants
    circ = validate_final_circulation_invariants(layout)
    circulation_valid = circ.get("circulation_valid", False)
    hard_violations = circ.get("hard_violations", [])
    unreachable_rooms = [v.get("room") for v in hard_violations if v.get("type") == "unreachable_room"]

    # Graph reachability check from exterior
    try:
        G = build_circulation_graph(layout)
        for r in layout.rooms:
            if r.type != 'parking':
                if r.id not in G or not nx.has_path(G, "exterior", r.id):
                    if r.id not in unreachable_rooms:
                        unreachable_rooms.append(r.id)
    except Exception as e:
        unreachable_rooms.append(f"graph_error: {str(e)}")

    passage_violations = [v for v in hard_violations if "passage" in v.get("type", "")]

    # 3. Door Feasibility Validation
    door_infeasible = False
    infeasible_doors: List[str] = []
    total_living_rooms = len([r for r in layout.rooms if r.type != 'parking'])
    if len(layout.doors) < max(0, total_living_rooms - 1):
        door_infeasible = True
        infeasible_doors.append(f"insufficient_doors: expected >= {total_living_rooms - 1}, found {len(layout.doors)}")

    for d in layout.doors:
        if d.width < 2.5:
            door_infeasible = True
            infeasible_doors.append(f"door_narrow_{d.from_room}_{d.to_room}: width={d.width}")
        r_from = next((r for r in layout.rooms if r.id == d.from_room), None)
        r_to = next((r for r in layout.rooms if r.id == d.to_room), None)
        if not r_from or not r_to:
            door_infeasible = True
            infeasible_doors.append(f"missing_door_endpoint_{d.from_room}_{d.to_room}")
        else:
            edge = get_shared_edge(
                {'x': r_from.x, 'y': r_from.y, 'width': r_from.width, 'depth': r_from.depth},
                {'x': r_to.x, 'y': r_to.y, 'width': r_to.width, 'depth': r_to.depth}
            )
            if not edge:
                door_infeasible = True
                infeasible_doors.append(f"no_shared_wall_{d.from_room}_{d.to_room}")
            else:
                edge_len = max(abs(edge['x2'] - edge['x1']), abs(edge['y2'] - edge['y1']))
                if edge_len < 2.5:
                    door_infeasible = True
                    infeasible_doors.append(f"short_shared_wall_{d.from_room}_{d.to_room}: {edge_len:.1f}ft")

    # 4. Room-Count Validity
    req_counts = dict(tc.rooms)
    if tc.parking:
        req_counts['parking'] = 1
    gen_counts: Dict[str, int] = {}
    for r in layout.rooms:
        base = r.type.split('_')[0]
        gen_counts[base] = gen_counts.get(base, 0) + 1

    room_count_mismatches: List[str] = []
    for r_type, req_n in req_counts.items():
        actual_n = gen_counts.get(r_type, 0)
        if actual_n != req_n:
            room_count_mismatches.append(f"{r_type}: expected {req_n}, actual {actual_n}")
    for r_type, actual_n in gen_counts.items():
        if r_type not in req_counts:
            room_count_mismatches.append(f"unexpected_{r_type}: {actual_n}")
    room_count_valid = len(room_count_mismatches) == 0

    # 5. Final Invariant Validation Object from Engine
    final_inv = opt_meta.get("final_invariant_validation", {})
    final_inv_engine_valid = final_inv.get("valid", False) if isinstance(final_inv, dict) else False

    # 6. Overall Hard Invariant Gate
    final_validation = bool(
        geometry_valid and
        circulation_valid and
        (len(unreachable_rooms) == 0) and
        (not door_infeasible) and
        (len(passage_violations) == 0) and
        room_count_valid and
        final_inv_engine_valid
    )

    # 7. Failure Reason Diagnostic
    failure_reason = None
    if not final_validation:
        if not geometry_valid:
            if len(overlaps) > 0:
                failure_reason = "ROOM_OVERLAP"
            elif len(boundary_violations) > 0:
                failure_reason = "OUTSIDE_PLOT_BOUNDARY"
            elif len(invalid_dimensions) > 0:
                failure_reason = "INVALID_DIMENSIONS"
            else:
                failure_reason = "GEOMETRY_INVALID"
        elif not room_count_valid:
            failure_reason = "ROOM_COUNT_MISMATCH"
        elif len(unreachable_rooms) > 0:
            failure_reason = "UNREACHABLE_ROOMS"
        elif door_infeasible:
            failure_reason = "DOOR_INFEASIBLE"
        elif len(passage_violations) > 0:
            failure_reason = "PASSAGE_VIOLATION"
        elif not circulation_valid:
            failure_reason = "CIRCULATION_INVALID"
        else:
            failure_reason = "FINAL_INVARIANT_FAILED"

    # Status: ONLY PASS when all hard invariants pass!
    status = "PASS" if final_validation else "FAIL"

    # Optimization and Vastu Scores (Separate from validity)
    selected_score = opt_meta.get("selected_score", None)
    if isinstance(vastu_result, dict):
        vastu_score = vastu_result.get("score", vastu_result.get("overall_score", 0))
    elif isinstance(vastu_result, (int, float)):
        vastu_score = vastu_result
    else:
        vastu_score = 0

    return {
        "status": status,
        "geometry_valid": geometry_valid,
        "circulation_valid": circulation_valid,
        "final_validation": final_validation,
        "unreachable_rooms": unreachable_rooms,
        "door_infeasible": door_infeasible,
        "infeasible_doors": infeasible_doors,
        "passage_violations": passage_violations,
        "room_count_valid": room_count_valid,
        "room_count_mismatches": room_count_mismatches,
        "invalid_dimensions": invalid_dimensions,
        "overlaps": overlaps,
        "boundary_violations": boundary_violations,
        "selected_score": selected_score,
        "vastu_score": vastu_score,
        "failure_reason": failure_reason
    }


if __name__ == "__main__":
    results_summary = []
    all_passed = True

    for i, tc in enumerate(test_cases):
        tc_display_name = getattr(tc, "test_case_name", f"TC{i+1}")
        print(f"\n{'='*50}")
        print(f"Running {tc_display_name} ({tc.plot.width}x{tc.plot.depth} {tc.plot.facing})")
        print(f"{'='*50}")

        try:
            layout = generate_layout(tc)
            vastu = analyze_vastu(layout)
            best_layout, best_vastu, opt_meta = optimize_layout(tc, layout, vastu)

            eval_res = evaluate_floorplan_invariants(tc, best_layout, opt_meta, best_vastu)
            eval_res["name"] = tc_display_name
            eval_res["tc_obj"] = tc
            results_summary.append(eval_res)

            print(f"\n{tc_display_name}")
            print("-" * 40)
            print(f"Status: {eval_res['status']}")
            print(f"Geometry valid: {eval_res['geometry_valid']}")
            print(f"Circulation valid: {eval_res['circulation_valid']}")
            print(f"Final validation: {eval_res['final_validation']}")
            print(f"Unreachable rooms: {eval_res['unreachable_rooms']}")
            print(f"Door infeasible: {eval_res['door_infeasible']}")
            print(f"Passage violations: {eval_res['passage_violations']}")
            print(f"Room count valid: {eval_res['room_count_valid']}")
            print(f"Selected score: {eval_res['selected_score']}")
            print(f"Vastu score: {eval_res['vastu_score']}")
            if eval_res['failure_reason']:
                print(f"Failure reason: {eval_res['failure_reason']}")

            if eval_res['status'] != "PASS":
                all_passed = False

        except Exception as e:
            import traceback
            traceback.print_exc()
            eval_res = {
                "name": tc_display_name,
                "status": "FAIL",
                "geometry_valid": False,
                "circulation_valid": False,
                "final_validation": False,
                "unreachable_rooms": ["EXCEPTION"],
                "door_infeasible": True,
                "infeasible_doors": [str(e)],
                "passage_violations": [],
                "room_count_valid": False,
                "room_count_mismatches": [],
                "invalid_dimensions": [],
                "overlaps": [],
                "boundary_violations": [],
                "selected_score": None,
                "vastu_score": None,
                "failure_reason": f"EXCEPTION: {str(e)}"
            }
            results_summary.append(eval_res)
            all_passed = False

    print("\n" + "=" * 60)
    print("PHASE 3G — PROCEDURAL REGRESSION INVARIANT SUMMARY")
    print("=" * 60)
    for r in results_summary:
        print(f"\n{r['name']}:")
        print(f"  Status: {r['status']}")
        print(f"  Geometry valid: {r['geometry_valid']}")
        print(f"  Circulation valid: {r['circulation_valid']}")
        print(f"  Final validation: {r['final_validation']}")
        print(f"  Room count valid: {r['room_count_valid']}")
        print(f"  Unreachable rooms: {r['unreachable_rooms']}")
        print(f"  Door infeasible: {r['door_infeasible']}")
        print(f"  Passage violations: {len(r['passage_violations'])}")
        print(f"  Selected score: {r['selected_score']}")
        print(f"  Vastu score: {r['vastu_score']}")
        if r.get('failure_reason'):
            print(f"  Failure reason: {r['failure_reason']}")
    print("=" * 60 + "\n")

    if not all_passed:
        print("[FAIL] REGRESSION FAILURE: One or more test cases failed hard invariants.")
        sys.exit(1)
    else:
        print("[PASS] ALL PROCEDURAL REGRESSION TEST CASES PASSED HARD INVARIANTS.")
        sys.exit(0)