import sys
import os
import json
import time
from typing import Dict, Any, List, Optional, Tuple

project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_dir not in sys.path:
    sys.path.insert(0, project_dir)

from models.requirements import FloorPlanRequirements, Plot
from models.floorplan import FloorPlan
from agents.orchestrator import FloorPlanOrchestrator
from agents.state import OrchestrationStatus, FailureClassification
from layout.generator import generate_layout
from layout.vastu_optimizer import optimize_layout
from layout.validator import validate_layout
from layout.architecture import validate_final_circulation_invariants, build_circulation_graph
from geometry.geometry_utils import get_shared_edge
from vastu import analyze_vastu
import networkx as nx

# Bounded, controlled Phase 3H evaluation matrix (26 scenarios)
TEST_SCENARIOS = [
    # 1. Baseline Regression Matrix (TC1–TC4)
    {
        "case_id": "TC1",
        "category": "baseline",
        "plot_width": 30, "plot_depth": 40, "facing": "west", "parking": True,
        "rooms": {"bedroom": 2, "hall": 1, "kitchen": 1, "bathroom": 2, "pooja": 1},
        "vastu_enabled": True, "vastu_optimization": True,
        "expected_status": "VALID",
        "description": "Standard 30x40 West 2BHK+Pooja baseline"
    },
    {
        "case_id": "TC2",
        "category": "baseline",
        "plot_width": 40, "plot_depth": 50, "facing": "east", "parking": True,
        "rooms": {"bedroom": 3, "hall": 1, "kitchen": 1, "bathroom": 2},
        "vastu_enabled": True, "vastu_optimization": True,
        "expected_status": "VALID",
        "description": "Standard 40x50 East 3BHK baseline"
    },
    {
        "case_id": "TC3",
        "category": "baseline",
        "plot_width": 30, "plot_depth": 50, "facing": "north", "parking": True,
        "rooms": {"bedroom": 2, "hall": 1, "kitchen": 2, "bathroom": 1, "pooja": 1},
        "vastu_enabled": True, "vastu_optimization": True,
        "expected_status": "VALID",
        "description": "Standard 30x50 North 2BHK+2Kit baseline"
    },
    {
        "case_id": "TC4",
        "category": "baseline",
        "plot_width": 30, "plot_depth": 40, "facing": "west", "parking": True,
        "rooms": {"bedroom": 1, "hall": 1, "kitchen": 1, "bathroom": 1},
        "vastu_enabled": True, "vastu_optimization": True,
        "expected_status": "VALID",
        "description": "Standard 30x40 West 1BHK baseline"
    },

    # 2. Plot-Size Sensitivity Matrix (Constant 2BHK+Pooja, Parking=Yes, Facing=South)
    {
        "case_id": "Plot-20x30",
        "category": "plot_size",
        "plot_width": 20, "plot_depth": 30, "facing": "south", "parking": True,
        "rooms": {"bedroom": 2, "hall": 1, "kitchen": 1, "bathroom": 2, "pooja": 1},
        "vastu_enabled": True, "vastu_optimization": True,
        "expected_status": None,
        "description": "Plot-size sensitivity: 20x30 (600 sq.ft) with 2BHK+Pooja"
    },
    {
        "case_id": "Plot-25x40",
        "category": "plot_size",
        "plot_width": 25, "plot_depth": 40, "facing": "south", "parking": True,
        "rooms": {"bedroom": 2, "hall": 1, "kitchen": 1, "bathroom": 2, "pooja": 1},
        "vastu_enabled": True, "vastu_optimization": True,
        "expected_status": "INFEASIBLE_REQUEST",
        "description": "Plot-size sensitivity: 25x40 South stress baseline"
    },
    {
        "case_id": "Plot-30x40",
        "category": "plot_size",
        "plot_width": 30, "plot_depth": 40, "facing": "south", "parking": True,
        "rooms": {"bedroom": 2, "hall": 1, "kitchen": 1, "bathroom": 2, "pooja": 1},
        "vastu_enabled": True, "vastu_optimization": True,
        "expected_status": None,
        "description": "Plot-size sensitivity: 30x40 South"
    },
    {
        "case_id": "Plot-30x50",
        "category": "plot_size",
        "plot_width": 30, "plot_depth": 50, "facing": "south", "parking": True,
        "rooms": {"bedroom": 2, "hall": 1, "kitchen": 1, "bathroom": 2, "pooja": 1},
        "vastu_enabled": True, "vastu_optimization": True,
        "expected_status": None,
        "description": "Plot-size sensitivity: 30x50 South"
    },
    {
        "case_id": "Plot-40x50",
        "category": "plot_size",
        "plot_width": 40, "plot_depth": 50, "facing": "south", "parking": True,
        "rooms": {"bedroom": 2, "hall": 1, "kitchen": 1, "bathroom": 2, "pooja": 1},
        "vastu_enabled": True, "vastu_optimization": True,
        "expected_status": None,
        "description": "Plot-size sensitivity: 40x50 South"
    },
    {
        "case_id": "Plot-40x60",
        "category": "plot_size",
        "plot_width": 40, "plot_depth": 60, "facing": "south", "parking": True,
        "rooms": {"bedroom": 2, "hall": 1, "kitchen": 1, "bathroom": 2, "pooja": 1},
        "vastu_enabled": True, "vastu_optimization": True,
        "expected_status": None,
        "description": "Plot-size sensitivity: 40x60 South"
    },
    {
        "case_id": "Plot-50x60",
        "category": "plot_size",
        "plot_width": 50, "plot_depth": 60, "facing": "south", "parking": True,
        "rooms": {"bedroom": 2, "hall": 1, "kitchen": 1, "bathroom": 2, "pooja": 1},
        "vastu_enabled": True, "vastu_optimization": True,
        "expected_status": None,
        "description": "Plot-size sensitivity: 50x60 South"
    },

    # 3. Parking Sensitivity Matrix (25x40 South 2BHK+Pooja)
    {
        "case_id": "Parking-Yes",
        "category": "parking_sensitivity",
        "plot_width": 25, "plot_depth": 40, "facing": "south", "parking": True,
        "rooms": {"bedroom": 2, "hall": 1, "kitchen": 1, "bathroom": 2, "pooja": 1},
        "vastu_enabled": True, "vastu_optimization": True,
        "expected_status": "INFEASIBLE_REQUEST",
        "description": "Parking sensitivity: 25x40 South with Parking"
    },
    {
        "case_id": "Parking-No",
        "category": "parking_sensitivity",
        "plot_width": 25, "plot_depth": 40, "facing": "south", "parking": False,
        "rooms": {"bedroom": 2, "hall": 1, "kitchen": 1, "bathroom": 2, "pooja": 1},
        "vastu_enabled": True, "vastu_optimization": True,
        "expected_status": None,
        "description": "Parking sensitivity: 25x40 South WITHOUT Parking"
    },

    # 4. Room-Count Sensitivity Matrix (25x40 South, Parking=Yes)
    {
        "case_id": "Room-2B1K2B1P",
        "category": "room_count_sensitivity",
        "plot_width": 25, "plot_depth": 40, "facing": "south", "parking": True,
        "rooms": {"bedroom": 2, "hall": 1, "kitchen": 1, "bathroom": 2, "pooja": 1},
        "vastu_enabled": True, "vastu_optimization": True,
        "expected_status": "INFEASIBLE_REQUEST",
        "description": "Room count: 2 Bed, 1 Kit, 2 Bath, 1 Pooja (reference)"
    },
    {
        "case_id": "Room-1B1K2B1P",
        "category": "room_count_sensitivity",
        "plot_width": 25, "plot_depth": 40, "facing": "south", "parking": True,
        "rooms": {"bedroom": 1, "hall": 1, "kitchen": 1, "bathroom": 2, "pooja": 1},
        "vastu_enabled": True, "vastu_optimization": True,
        "expected_status": None,
        "description": "Room count: 1 Bed, 1 Kit, 2 Bath, 1 Pooja"
    },
    {
        "case_id": "Room-2B1K2B0P",
        "category": "room_count_sensitivity",
        "plot_width": 25, "plot_depth": 40, "facing": "south", "parking": True,
        "rooms": {"bedroom": 2, "hall": 1, "kitchen": 1, "bathroom": 2},
        "vastu_enabled": True, "vastu_optimization": True,
        "expected_status": None,
        "description": "Room count: 2 Bed, 1 Kit, 2 Bath, 0 Pooja"
    },
    {
        "case_id": "Room-1B1K1B0P",
        "category": "room_count_sensitivity",
        "plot_width": 25, "plot_depth": 40, "facing": "south", "parking": True,
        "rooms": {"bedroom": 1, "hall": 1, "kitchen": 1, "bathroom": 1},
        "vastu_enabled": True, "vastu_optimization": True,
        "expected_status": None,
        "description": "Room count: 1 Bed, 1 Kit, 1 Bath, 0 Pooja"
    },

    # 5. Facing-Direction Sensitivity Matrix (25x40, 2BHK+Pooja, Parking=Yes)
    {
        "case_id": "Facing-South",
        "category": "facing_sensitivity",
        "plot_width": 25, "plot_depth": 40, "facing": "south", "parking": True,
        "rooms": {"bedroom": 2, "hall": 1, "kitchen": 1, "bathroom": 2, "pooja": 1},
        "vastu_enabled": True, "vastu_optimization": True,
        "expected_status": "INFEASIBLE_REQUEST",
        "description": "Facing sensitivity: South facing"
    },
    {
        "case_id": "Facing-North",
        "category": "facing_sensitivity",
        "plot_width": 25, "plot_depth": 40, "facing": "north", "parking": True,
        "rooms": {"bedroom": 2, "hall": 1, "kitchen": 1, "bathroom": 2, "pooja": 1},
        "vastu_enabled": True, "vastu_optimization": True,
        "expected_status": None,
        "description": "Facing sensitivity: North facing"
    },
    {
        "case_id": "Facing-East",
        "category": "facing_sensitivity",
        "plot_width": 25, "plot_depth": 40, "facing": "east", "parking": True,
        "rooms": {"bedroom": 2, "hall": 1, "kitchen": 1, "bathroom": 2, "pooja": 1},
        "vastu_enabled": True, "vastu_optimization": True,
        "expected_status": None,
        "description": "Facing sensitivity: East facing"
    },
    {
        "case_id": "Facing-West",
        "category": "facing_sensitivity",
        "plot_width": 25, "plot_depth": 40, "facing": "west", "parking": True,
        "rooms": {"bedroom": 2, "hall": 1, "kitchen": 1, "bathroom": 2, "pooja": 1},
        "vastu_enabled": True, "vastu_optimization": True,
        "expected_status": None,
        "description": "Facing sensitivity: West facing"
    },

    # 6. Vastu Sensitivity Matrix (25x40 South 2BHK+Pooja, Parking=Yes)
    {
        "case_id": "Vastu-ON",
        "category": "vastu_sensitivity",
        "plot_width": 25, "plot_depth": 40, "facing": "south", "parking": True,
        "rooms": {"bedroom": 2, "hall": 1, "kitchen": 1, "bathroom": 2, "pooja": 1},
        "vastu_enabled": True, "vastu_optimization": True,
        "expected_status": "INFEASIBLE_REQUEST",
        "description": "Vastu sensitivity: Vastu ON"
    },
    {
        "case_id": "Vastu-OFF",
        "category": "vastu_sensitivity",
        "plot_width": 25, "plot_depth": 40, "facing": "south", "parking": True,
        "rooms": {"bedroom": 2, "hall": 1, "kitchen": 1, "bathroom": 2, "pooja": 1},
        "vastu_enabled": False, "vastu_optimization": False,
        "expected_status": None,
        "description": "Vastu sensitivity: Vastu OFF (geometry-only evaluation)"
    },

    # 7. Repeatability Runs
    {
        "case_id": "Repeat-TC1",
        "category": "repeatability",
        "plot_width": 30, "plot_depth": 40, "facing": "west", "parking": True,
        "rooms": {"bedroom": 2, "hall": 1, "kitchen": 1, "bathroom": 2, "pooja": 1},
        "vastu_enabled": True, "vastu_optimization": True,
        "expected_status": "VALID",
        "description": "Repeatability: TC1 second run"
    },
    {
        "case_id": "Repeat-TC2",
        "category": "repeatability",
        "plot_width": 40, "plot_depth": 50, "facing": "east", "parking": True,
        "rooms": {"bedroom": 3, "hall": 1, "kitchen": 1, "bathroom": 2},
        "vastu_enabled": True, "vastu_optimization": True,
        "expected_status": "VALID",
        "description": "Repeatability: TC2 second run"
    },
    {
        "case_id": "Repeat-25x40-South",
        "category": "repeatability",
        "plot_width": 25, "plot_depth": 40, "facing": "south", "parking": True,
        "rooms": {"bedroom": 2, "hall": 1, "kitchen": 1, "bathroom": 2, "pooja": 1},
        "vastu_enabled": True, "vastu_optimization": True,
        "expected_status": "INFEASIBLE_REQUEST",
        "description": "Repeatability: 25x40 South stress second run"
    }
]

def evaluate_candidate_invariants(reqs: FloorPlanRequirements, layout: Optional[FloorPlan]) -> Dict[str, Any]:
    """
    Evaluates independent hard geometric and architectural invariants for a candidate.
    """
    if layout is None:
        return {
            "geometry_valid": False,
            "circulation_valid": False,
            "final_valid": False,
            "unreachable_rooms": [],
            "passage_violations": [],
            "door_infeasible": True,
            "room_count_valid": False
        }

    # 1. Geometry Validation
    val = validate_layout(layout)
    errors = val.get("errors", [])
    overlaps = [e for e in errors if "overlap" in e.lower()]
    boundary_violations = [e for e in errors if "outside" in e.lower() or "boundary" in e.lower()]
    invalid_dimensions = [e for e in errors if "dimension" in e.lower()]
    geometry_valid = bool(val.get("valid", False) and len(overlaps) == 0 and len(boundary_violations) == 0 and len(invalid_dimensions) == 0)

    # 2. Circulation & Invariants
    circ = validate_final_circulation_invariants(layout)
    circulation_valid = bool(circ.get("circulation_valid", False))
    hard_violations = circ.get("hard_violations", [])
    unreachable_rooms = [v.get("room") for v in hard_violations if v.get("type") == "unreachable_room"]

    # Graph reachability
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

    # 3. Door Feasibility
    door_infeasible = False
    total_living_rooms = len([r for r in layout.rooms if r.type != 'parking'])
    if len(layout.doors) < max(0, total_living_rooms - 1):
        door_infeasible = True

    for d in layout.doors:
        if d.width < 2.5:
            door_infeasible = True
        r_from = next((r for r in layout.rooms if r.id == d.from_room), None)
        r_to = next((r for r in layout.rooms if r.id == d.to_room), None)
        if not r_from or not r_to:
            door_infeasible = True
        else:
            edge = get_shared_edge(
                {'x': r_from.x, 'y': r_from.y, 'width': r_from.width, 'depth': r_from.depth},
                {'x': r_to.x, 'y': r_to.y, 'width': r_to.width, 'depth': r_to.depth}
            )
            if not edge:
                door_infeasible = True
            else:
                edge_len = max(abs(edge['x2'] - edge['x1']), abs(edge['y2'] - edge['y1']))
                if edge_len < 2.5:
                    door_infeasible = True

    # 4. Room-Count Validity
    req_counts = dict(reqs.rooms)
    if reqs.parking:
        req_counts['parking'] = 1
    gen_counts: Dict[str, int] = {}
    for r in layout.rooms:
        base = r.type.split('_')[0]
        gen_counts[base] = gen_counts.get(base, 0) + 1

    room_count_valid = True
    for r_type, req_n in req_counts.items():
        if gen_counts.get(r_type, 0) != req_n:
            room_count_valid = False
            break

    final_valid = bool(
        geometry_valid and
        circulation_valid and
        len(unreachable_rooms) == 0 and
        not door_infeasible and
        len(passage_violations) == 0 and
        room_count_valid
    )

    return {
        "geometry_valid": geometry_valid,
        "circulation_valid": circulation_valid,
        "final_valid": final_valid,
        "unreachable_rooms": unreachable_rooms,
        "passage_violations": passage_violations,
        "door_infeasible": door_infeasible,
        "room_count_valid": room_count_valid
    }

def run_procedural_pipeline(reqs: FloorPlanRequirements, vastu_enabled: bool, vastu_opt: bool) -> Tuple[str, bool, Optional[FloorPlan]]:
    """
    Executes the existing procedural generation pipeline.
    """
    try:
        layout = generate_layout(reqs)
        if vastu_enabled:
            vastu_report = analyze_vastu(layout)
            if vastu_opt:
                try:
                    best_layout, best_vastu, opt_meta = optimize_layout(reqs, layout, vastu_report)
                    layout = best_layout
                except Exception:
                    pass
        val = evaluate_candidate_invariants(reqs, layout)
        if val["final_valid"]:
            return "PASS", True, layout
        else:
            return "FAIL", False, layout
    except Exception:
        return "FAIL", False, None

def run_robustness_harness():
    print("=" * 70)
    print("PHASE 3H — ROBUSTNESS & CONSTRAINT-SENSITIVITY EVALUATION HARNESS")
    print("=" * 70)
    print(f"Total Controlled Scenarios: {len(TEST_SCENARIOS)}\n")

    orchestrator = FloorPlanOrchestrator()
    reports_dir = os.path.join(project_dir, "reports")
    os.makedirs(reports_dir, exist_ok=True)

    results_data: List[Dict[str, Any]] = []
    category_summary: Dict[str, Dict[str, int]] = {}
    
    total_valid = 0
    total_retryable = 0
    total_infeasible = 0
    total_failed = 0
    invalid_plans_rendered = 0
    critical_regressions = []

    procedural_comparison_cases = [
        "TC1", "TC2", "TC3", "TC4", "Plot-25x40", "Parking-No"
    ]
    procedural_results: Dict[str, Dict[str, Any]] = {}

    start_time = time.time()

    for idx, sc in enumerate(TEST_SCENARIOS):
        case_id = sc["case_id"]
        category = sc["category"]
        w = sc["plot_width"]
        d = sc["plot_depth"]
        facing = sc["facing"]
        parking = sc["parking"]
        rooms = sc["rooms"]
        vastu_enabled = sc["vastu_enabled"]
        vastu_opt = sc["vastu_optimization"]

        reqs = FloorPlanRequirements(
            plot=Plot(width=w, depth=d, facing=facing, unit="ft"),
            rooms=rooms,
            parking=parking,
            request_id=f"p3h_{case_id}"
        )

        user_prompt = f"{w}x{d} {facing} facing with {', '.join(f'{v} {k}' for k, v in rooms.items())}{' with parking' if parking else ''}"

        # Execute Agentic Orchestrator
        t0 = time.time()
        state = orchestrator.run(
            user_prompt=user_prompt,
            enable_vastu=vastu_enabled,
            enable_optimizer=vastu_opt,
            request_id=f"p3h_{case_id}",
            requirements=reqs
        )
        elapsed = round((time.time() - t0), 2)

        # Status and Validation
        orch_status = state.orchestration_status.value
        fail_class = state.failure_classification.value
        candidate = state.selected_candidate

        # Independent invariant check
        inv_results = evaluate_candidate_invariants(reqs, candidate)
        final_valid = inv_results["final_valid"]

        # HARD SAFETY INVARIANT: An invalid plan must NEVER be rendered
        # In the web app: plan is only rendered if state.is_valid and final_valid
        can_render = bool(state.is_valid and candidate and final_valid)
        if not final_valid and state.is_valid:
            invalid_plans_rendered += 1
            critical_regressions.append(f"CRITICAL REGRESSION on {case_id}: Layout failed invariants but state.is_valid is True!")
        
        rendered = can_render

        # VALIDITY INVARIANT: If classified VALID, all hard constraints MUST be satisfied
        if orch_status == "VALID":
            if not final_valid:
                critical_regressions.append(f"CRITICAL REGRESSION on {case_id}: Classified VALID but failed hard invariants: {inv_results}")

        # CLASSIFICATION CONSISTENCY CHECK: If INFEASIBLE_REQUEST, verify meaningful explanation and no render
        if orch_status == "INFEASIBLE_REQUEST":
            if not state.diagnosis_reason:
                critical_regressions.append(f"CRITICAL REGRESSION on {case_id}: Classified INFEASIBLE_REQUEST without diagnosis_reason!")
            if rendered:
                critical_regressions.append(f"CRITICAL REGRESSION on {case_id}: Classified INFEASIBLE_REQUEST but marked for rendering!")

        # Check against expected status if explicitly asserted
        expected_status = sc.get("expected_status")
        if expected_status:
            if orch_status != expected_status:
                print(f"[NOTE] Expected/Observed discrepancy on {case_id}: Expected {expected_status}, got {orch_status}")

        # Collect metrics
        structural_ev = state.structural_evidence or {}
        comp_candidates = structural_ev.get("complete_candidates")
        circ_valid_candidates = structural_ev.get("circulation_valid_candidates")
        door_feas_candidates = structural_ev.get("door_feasible_candidates")
        geo_valid_candidates = structural_ev.get("geometry_valid_candidates")
        conn_valid_candidates = structural_ev.get("connectivity_valid_candidates")

        vastu_score = state.vastu_result.metrics.get("score") if state.vastu_result else None
        arch_score = state.architecture_result.metrics.get("architectural_score") if state.architecture_result else None
        space_util = round(candidate.utilization_percentage, 1) if candidate else None
        compactness = round(candidate.compactness, 2) if (candidate and hasattr(candidate, "compactness")) else None

        # Build case report
        case_report = {
            "case_id": case_id,
            "category": category,
            "description": sc["description"],
            "input": {
                "plot_width": w,
                "plot_depth": d,
                "facing": facing,
                "parking": parking,
                "bedrooms": rooms.get("bedroom", 0),
                "hall": rooms.get("hall", 0),
                "kitchens": rooms.get("kitchen", 0),
                "bathrooms": rooms.get("bathroom", 0),
                "pooja": rooms.get("pooja", 0),
                "vastu_enabled": vastu_enabled,
                "vastu_optimization": vastu_opt
            },
            "result": {
                "orchestration_status": orch_status,
                "failure_classification": fail_class,
                "valid": final_valid,
                "rendered": rendered,
                "attempted_iterations": state.attempted_iterations,
                "retry_recommended": state.retry_recommended,
                "dominant_issue": structural_ev.get("dominant_issue") or state.status,
                "affected_rooms": state.affected_rooms,
                "diagnosis_reason": state.diagnosis_reason,
                "infeasibility_reasons": state.infeasibility_reasons,
                "recommended_relaxations": state.recommended_relaxations,
                "duration_seconds": elapsed
            },
            "metrics": {
                "complete_candidates": comp_candidates,
                "geometry_valid_candidates": geo_valid_candidates,
                "connectivity_valid_candidates": conn_valid_candidates,
                "circulation_valid_candidates": circ_valid_candidates,
                "door_feasible_candidates": door_feas_candidates,
                "space_utilization": space_util,
                "compactness": compactness,
                "vastu_score": vastu_score,
                "architecture_score": arch_score,
                "final_score": vastu_score if vastu_score is not None else None
            },
            "validation": {
                "geometry_valid": inv_results["geometry_valid"],
                "circulation_valid": inv_results["circulation_valid"],
                "final_valid": inv_results["final_valid"],
                "unreachable_rooms": inv_results["unreachable_rooms"],
                "passage_violations": inv_results["passage_violations"],
                "door_infeasible": inv_results["door_infeasible"],
                "room_count_valid": inv_results["room_count_valid"]
            }
        }
        results_data.append(case_report)

        # Aggregate counts
        if orch_status == "VALID":
            total_valid += 1
        elif orch_status == "RETRYABLE_FAILURE":
            total_retryable += 1
        elif orch_status == "INFEASIBLE_REQUEST":
            total_infeasible += 1
        else:
            total_failed += 1

        cat_d = category_summary.setdefault(category, {"VALID": 0, "INFEASIBLE_REQUEST": 0, "RETRYABLE_FAILURE": 0, "FAILED": 0})
        cat_d[orch_status] = cat_d.get(orch_status, 0) + 1

        # Check if procedural comparison is requested
        if case_id in procedural_comparison_cases:
            proc_status, proc_valid, _ = run_procedural_pipeline(reqs, vastu_enabled, vastu_opt)
            procedural_results[case_id] = {
                "agentic_status": orch_status,
                "agentic_valid": final_valid,
                "procedural_status": proc_status,
                "procedural_valid": proc_valid
            }

        # Terminal live progress
        status_symbol = "[VALID]" if orch_status == "VALID" else f"[{orch_status}]"
        print(f"[{idx+1:02d}/{len(TEST_SCENARIOS)}] {case_id:<22} -> {status_symbol:<22} ({elapsed}s)")

    total_time = round(time.time() - start_time, 2)

    # Save to JSON
    json_path = os.path.join(reports_dir, "phase3h_robustness.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({
            "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "total_cases": len(TEST_SCENARIOS),
            "summary": {
                "valid": total_valid,
                "retryable_failure": total_retryable,
                "infeasible_request": total_infeasible,
                "failed": total_failed,
                "invalid_plans_rendered": invalid_plans_rendered,
                "total_duration_seconds": total_time
            },
            "procedural_comparison": procedural_results,
            "cases": results_data
        }, f, indent=2)

    # Print Terminal Summary
    print("\n" + "=" * 70)
    print("PHASE 3H — ROBUSTNESS EVALUATION SUMMARY TABLE")
    print("=" * 70)
    print(f"{'CASE ID':<20} | {'CATEGORY':<24} | {'STATUS':<20} | {'RENDER'}")
    print("-" * 70)
    for r in results_data:
        rend_str = "YES (VALID)" if r["result"]["rendered"] else "NO (SUPPRESSED)"
        print(f"{r['case_id']:<20} | {r['category']:<24} | {r['result']['orchestration_status']:<20} | {rend_str}")

    print("\n" + "=" * 70)
    print("CATEGORY BREAKDOWN")
    print("=" * 70)
    for cat, counts in category_summary.items():
        print(f"  {cat:<26}: VALID={counts.get('VALID', 0)}, INFEASIBLE={counts.get('INFEASIBLE_REQUEST', 0)}, RETRYABLE={counts.get('RETRYABLE_FAILURE', 0)}, FAILED={counts.get('FAILED', 0)}")

    print("\n" + "=" * 70)
    print("AGENTIC VS PROCEDURAL PIPELINE COMPARISON")
    print("=" * 70)
    print(f"{'CASE ID':<18} | {'AGENTIC STATUS':<20} | {'PROCEDURAL STATUS':<20} | {'MATCH'}")
    print("-" * 70)
    for cid, cmp_d in procedural_results.items():
        match_str = "CONSISTENT" if (cmp_d["agentic_valid"] == cmp_d["procedural_valid"]) else "DIVERGENT"
        print(f"{cid:<18} | {cmp_d['agentic_status']:<20} | {cmp_d['procedural_status']:<20} | {match_str}")

    print("\n" + "=" * 70)
    print("AGGREGATED SUMMARY")
    print("=" * 70)
    print(f"Total test scenarios:      {len(TEST_SCENARIOS)}")
    print(f"VALID:                     {total_valid}")
    print(f"RETRYABLE_FAILURE:         {total_retryable}")
    print(f"INFEASIBLE_REQUEST:        {total_infeasible}")
    print(f"FAILED:                    {total_failed}")
    print(f"Invalid plans rendered:    {invalid_plans_rendered}")
    print(f"Total evaluation duration: {total_time}s")
    print(f"Machine-readable report:   {json_path}")
    print("=" * 70)

    if critical_regressions:
        print("\n[CRITICAL REGRESSIONS DETECTED]")
        for cr in critical_regressions:
            print(f"  - {cr}")
        sys.exit(1)
    else:
        print("\n[SAFETY INVARIANT VERIFIED] Invalid plans rendered: 0. All hard constraints strictly upheld.")
        return 0

if __name__ == "__main__":
    run_robustness_harness()
