"""
Phase 4G: Adaptive Circulation Topology Tests
Validates that:
1. 25x40 South-facing stress case succeeds with an adaptive circulation spine.
2. Circulation is adaptive (fallback) and NOT added when star topology suffices.
3. Invariants are preserved: entrance -> hall_1, vehicle gate -> parking_1.
4. Privacy: no private room acts as common passage.
5. Geometry and door feasibility are strictly maintained.
6. Multi-agent orchestrator runs successfully on circulation layouts.
"""

import pytest
from models.requirements import FloorPlanRequirements, Plot
from layout.generator import generate_layout, generate_layout_beam_search
from layout.validator import validate_layout
from layout.architecture import (
    validate_final_circulation_invariants,
    validate_circulation_constraints,
    evaluate_architecture,
    build_circulation_graph
)
from agents.orchestrator import FloorPlanOrchestrator
from agents.state import OrchestrationStatus
import networkx as nx


@pytest.fixture
def stress_case_reqs():
    return FloorPlanRequirements(
        plot=Plot(width=25, depth=40, facing="south", unit="ft"),
        rooms={"bedroom": 2, "hall": 1, "kitchen": 1, "bathroom": 2, "pooja": 1},
        parking=True,
        request_id="phase4g_25x40_south"
    )


def test_1_stress_case_25x40_south_valid_with_circulation(stress_case_reqs):
    """Test 1: 25x40 South full program produces a valid layout with circulation."""
    plan = generate_layout(stress_case_reqs)
    assert plan is not None, "Failed to generate layout for 25x40 South"
    
    val = validate_layout(plan)
    assert val.get("valid") is True, f"Layout validation failed: {val.get('errors')}"
    
    room_types = [r.type for r in plan.rooms]
    assert "circulation" in room_types, "Circulation entity must be present in 25x40 South"
    circ_room = next(r for r in plan.rooms if r.type == "circulation")
    assert circ_room.id == "circulation_1"
    assert circ_room.width >= 3.0
    assert circ_room.depth >= 3.0


def test_2_main_entrance_to_hall(stress_case_reqs):
    """Test 2: Main entrance remains exterior -> hall_1."""
    plan = generate_layout(stress_case_reqs)
    assert plan is not None
    assert plan.entrance is not None
    assert plan.entrance.side.lower() == "south"
    assert plan.entrance.room == "hall_1"
    assert plan.entrance.width >= 3.0
    assert plan.entrance.y == 40.0


def test_3_vehicle_gate_to_parking(stress_case_reqs):
    """Test 3: Vehicle gate remains exterior -> parking_1."""
    plan = generate_layout(stress_case_reqs)
    assert plan is not None
    assert getattr(plan, "vehicle_gate", None) is not None
    assert plan.vehicle_gate.side.lower() == "south"
    assert plan.vehicle_gate.room == "parking_1"
    assert plan.vehicle_gate.width >= 8.0
    assert plan.vehicle_gate.y == 40.0


def test_4_circulation_connectivity(stress_case_reqs):
    """Test 4: Circulation connects to hall_1 and reaches all downstream required rooms."""
    plan = generate_layout(stress_case_reqs)
    assert plan is not None
    
    G = build_circulation_graph(plan)
    assert G.has_edge("hall_1", "circulation_1"), "hall_1 must directly connect to circulation_1"
    
    # Verify all rooms are reachable from exterior and hall_1
    for r in plan.rooms:
        if r.type != "parking":
            assert nx.has_path(G, "exterior", r.id), f"Room {r.id} is not reachable from exterior"
            assert nx.has_path(G, "hall_1", r.id), f"Room {r.id} is not reachable from hall_1"


def test_5_privacy_invariants(stress_case_reqs):
    """Test 5: Bedrooms, kitchen, bathrooms are never used as general circulation passages."""
    plan = generate_layout(stress_case_reqs)
    assert plan is not None
    
    circ_val = validate_final_circulation_invariants(plan)
    assert circ_val.get("circulation_valid") is True, f"Hard violations: {circ_val.get('hard_violations')}"
    
    G = build_circulation_graph(plan)
    for node in G.nodes():
        if node in ["exterior", "parking_1", "hall_1", "circulation_1"]:
            continue
        # Private node: removal must not disconnect unrelated rooms
        node_type = next((r.type for r in plan.rooms if r.id == node), "")
        H = G.copy()
        H.remove_node(node)
        
        deps = []
        for other in G.nodes():
            if other != node and other != "exterior" and not other.startswith("parking"):
                if nx.has_path(G, "exterior", other) and not nx.has_path(H, "exterior", other):
                    deps.append(other)
                    
        if node_type == "bedroom":
            # Can only parent attached bathroom or dressing
            for d in deps:
                d_type = next(r.type for r in plan.rooms if r.id == d)
                assert d_type in ["bathroom", "balcony", "dressing"], f"Bedroom {node} acts as passage to {d} ({d_type})"
        elif node_type == "kitchen":
            for d in deps:
                d_type = next(r.type for r in plan.rooms if r.id == d)
                assert d_type in ["pooja", "dining", "utility"], f"Kitchen {node} acts as passage to {d} ({d_type})"
        elif node_type == "bathroom":
            assert len(deps) == 0, f"Bathroom {node} acts as passage to {deps}"


def test_6_geometry_validity(stress_case_reqs):
    """Test 6: Circulation is strictly inside plot, valid dimensions, no overlap."""
    plan = generate_layout(stress_case_reqs)
    assert plan is not None
    
    circ = next(r for r in plan.rooms if r.type == "circulation")
    assert circ.x >= 0.0
    assert circ.y >= 0.0
    assert circ.x + circ.width <= plan.plot_width + 0.01
    assert circ.y + circ.depth <= plan.plot_depth + 0.01
    assert circ.area >= 20.0
    
    # Overlap check
    from layout.generator import boxes_intersect
    for r in plan.rooms:
        if r.id != circ.id:
            c_dict = {'x': circ.x, 'y': circ.y, 'width': circ.width, 'depth': circ.depth}
            r_dict = {'x': r.x, 'y': r.y, 'width': r.width, 'depth': r.depth}
            assert not boxes_intersect(c_dict, r_dict), f"Circulation overlaps with {r.id}"


def test_7_door_feasibility(stress_case_reqs):
    """Test 7: Every door lies on shared boundary, has valid width >= 2.5 ft."""
    plan = generate_layout(stress_case_reqs)
    assert plan is not None
    
    assert len(plan.doors) >= 7, f"Expected at least 7 doors, got {len(plan.doors)}"
    for d in plan.doors:
        assert d.width >= 2.5, f"Door {d.id} width {d.width} < 2.5 ft"
        # Find connecting rooms
        r1 = next(r for r in plan.rooms if r.id == d.from_room)
        r2 = next(r for r in plan.rooms if r.id == d.to_room)
        from layout.generator import get_shared_edge
        edge = get_shared_edge(
            {'x': r1.x, 'y': r1.y, 'width': r1.width, 'depth': r1.depth},
            {'x': r2.x, 'y': r2.y, 'width': r2.width, 'depth': r2.depth}
        )
        assert edge is not None, f"Door {d.id} between {d.from_room} and {d.to_room} has no shared edge"
        edge_len = max(abs(edge['x2'] - edge['x1']), abs(edge['y2'] - edge['y1']))
        assert edge_len >= d.width, f"Door {d.id} width {d.width} exceeds shared edge {edge_len}"


def test_8_star_topology_preservation():
    """Test 8: Spacious layouts (e.g. TC1 30x40 West, TC2 40x50 East) do NOT add circulation."""
    reqs_tc1 = FloorPlanRequirements(
        plot=Plot(width=30, depth=40, facing="west", unit="ft"),
        rooms={"bedroom": 2, "hall": 1, "kitchen": 1, "bathroom": 2, "pooja": 1},
        parking=True,
        request_id="tc1_star_check"
    )
    plan_tc1 = generate_layout(reqs_tc1)
    assert plan_tc1 is not None
    types_tc1 = [r.type for r in plan_tc1.rooms]
    assert "circulation" not in types_tc1, "Circulation must NOT be added to TC1 (star topology suffices)"
    
    reqs_tc2 = FloorPlanRequirements(
        plot=Plot(width=40, depth=50, facing="east", unit="ft"),
        rooms={"bedroom": 3, "hall": 1, "kitchen": 1, "bathroom": 2},
        parking=True,
        request_id="tc2_star_check"
    )
    plan_tc2 = generate_layout(reqs_tc2)
    assert plan_tc2 is not None
    types_tc2 = [r.type for r in plan_tc2.rooms]
    assert "circulation" not in types_tc2, "Circulation must NOT be added to TC2 (star topology suffices)"


def test_9_procedural_regression_tc1_to_tc4():
    """Test 9: Procedural regression test cases TC1-TC4 all remain valid."""
    cases = [
        ("TC1", 30, 40, "west", {"bedroom": 2, "hall": 1, "kitchen": 1, "bathroom": 2, "pooja": 1}, True),
        ("TC2", 40, 50, "east", {"bedroom": 3, "hall": 1, "kitchen": 1, "bathroom": 2}, True),
        ("TC3", 30, 50, "north", {"bedroom": 2, "hall": 1, "kitchen": 2, "bathroom": 1, "pooja": 1}, True),
        ("TC4", 30, 40, "west", {"bedroom": 1, "hall": 1, "kitchen": 1, "bathroom": 1}, True),
    ]
    for name, w, d, facing, rooms, parking in cases:
        reqs = FloorPlanRequirements(
            plot=Plot(width=w, depth=d, facing=facing, unit="ft"),
            rooms=rooms,
            parking=parking,
            request_id=f"phase4g_reg_{name}"
        )
        plan = generate_layout(reqs)
        assert plan is not None, f"Failed to generate plan for {name}"
        val = validate_layout(plan)
        assert val.get("valid") is True, f"Validation failed for {name}: {val.get('errors')}"


def test_10_agentic_mode_orchestration(stress_case_reqs):
    """Test 10: Multi-agent orchestration on 25x40 South produces VALID status."""
    prompt = "I have 25x40 land. I want 2 bedrooms, 1 hall, 1 kitchen, 2 bathrooms, 1 pooja room and parking. House should face south."
    orchestrator = FloorPlanOrchestrator()
    state = orchestrator.run(
        user_prompt=prompt,
        enable_vastu=True,
        enable_optimizer=True,
        request_id="agentic_phase4g_test",
        requirements=stress_case_reqs
    )
    assert state.is_valid is True, f"Orchestrator returned is_valid=False: {state.error_message}"
    assert state.orchestration_status == OrchestrationStatus.VALID
    assert state.selected_candidate is not None
    assert any(r.type == "circulation" for r in state.selected_candidate.rooms)
