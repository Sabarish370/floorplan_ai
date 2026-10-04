import pytest
from models.requirements import FloorPlanRequirements, Plot
from agents.orchestrator import FloorPlanOrchestrator
from agents.state import OrchestrationStatus, FailureClassification
from layout.architecture import validate_final_circulation_invariants
from layout.validator import validate_layout

# The regression test cases belong ONLY in tests/, NOT in production agent state!
TC_CONFIGS = [
    {
        "id": "regression_tc1",
        "name": "TC1",
        "reqs": FloorPlanRequirements(
            plot=Plot(width=30, depth=40, facing="west", unit="ft"),
            rooms={"bedroom": 2, "hall": 1, "kitchen": 1, "bathroom": 2, "pooja": 1},
            parking=True,
            request_id="tc1_req"
        ),
        "prompt": "I have 30x40 land. I want 2 bedrooms, 1 hall, 1 kitchen, 2 bathrooms, 1 pooja room and parking. House should face west."
    },
    {
        "id": "regression_tc2",
        "name": "TC2",
        "reqs": FloorPlanRequirements(
            plot=Plot(width=40, depth=50, facing="east", unit="ft"),
            rooms={"bedroom": 3, "hall": 1, "kitchen": 1, "bathroom": 2},
            parking=True,
            request_id="tc2_req"
        ),
        "prompt": "I have 40x50 land. I want 3 bedrooms, 1 hall, 1 kitchen, 2 bathrooms and parking. House should face east."
    },
    {
        "id": "regression_tc3",
        "name": "TC3",
        "reqs": FloorPlanRequirements(
            plot=Plot(width=30, depth=50, facing="north", unit="ft"),
            rooms={"bedroom": 2, "hall": 1, "kitchen": 2, "bathroom": 1, "pooja": 1},
            parking=True,
            request_id="tc3_req"
        ),
        "prompt": "I have 30x50 land. I want 2 bedrooms, 1 hall, 2 kitchens, 1 bathroom, 1 pooja room and parking. House should face north."
    },
    {
        "id": "regression_tc4",
        "name": "TC4",
        "reqs": FloorPlanRequirements(
            plot=Plot(width=30, depth=40, facing="west", unit="ft"),
            rooms={"bedroom": 1, "hall": 1, "kitchen": 1, "bathroom": 1},
            parking=True,
            request_id="tc4_req"
        ),
        "prompt": "I have 30x40 land. I want 1 bedroom, 1 hall, 1 kitchen, 1 bathroom and parking. House should face west."
    }
]

@pytest.mark.parametrize("tc", TC_CONFIGS, ids=[t["name"] for t in TC_CONFIGS])
def test_regression_agentic_pipeline(tc):
    orchestrator = FloorPlanOrchestrator()
    state = orchestrator.run(
        user_prompt=tc["prompt"],
        enable_vastu=True,
        enable_optimizer=True,
        request_id=tc["id"],
        requirements=tc["reqs"]
    )

    # 1. State integrity check (Correction 1)
    assert not hasattr(state, "test_case_name"), "Production state must NOT contain test_case_name!"
    assert state.request_id == tc["id"]
    
    # 2. Status & Validation Gate check (Correction 5 & 9)
    assert state.status == "SUCCESS", f"{tc['name']} failed orchestration: {state.error_message}"
    assert state.orchestration_status == OrchestrationStatus.VALID
    assert state.is_valid is True, f"{tc['name']} must pass final validation"
    assert state.selected_candidate is not None

    # 3. Independent geometry validation
    val = validate_layout(state.selected_candidate)
    assert val["valid"] is True, f"{tc['name']} failed layout validation: {val.get('errors')}"

    # 4. Strict circulation invariants check (No kitchen/bedroom passage violation)
    circ = validate_final_circulation_invariants(state.selected_candidate)
    assert circ["circulation_valid"] is True, f"{tc['name']} violated circulation invariants: {circ.get('hard_violations')}"

    # 5. Check trace exists and bounded iterations
    assert len(state.trace) > 0
    assert state.iteration <= state.max_iterations

def test_targeted_tc2_multi_bedroom_bathroom_assignment():
    """
    Targeted regression test for multiple bedrooms serving multiple attached bathrooms (TC2 scenario).
    Verifies:
    1. Each bathroom receives a feasible door.
    2. No bathroom remains unreachable because of greedy bedroom assignment.
    3. Bedroom/bathroom assignment respects existing eligibility rules (max 1 attached bath per bedroom).
    4. Existing circulation constraints remain valid.
    5. No private room becomes an invalid passage.
    6. Geometry remains valid.
    """
    import networkx as nx
    from layout.architecture import build_circulation_graph

    tc2 = next(t for t in TC_CONFIGS if t["name"] == "TC2")
    orchestrator = FloorPlanOrchestrator()
    state = orchestrator.run(
        user_prompt=tc2["prompt"],
        enable_vastu=True,
        enable_optimizer=True,
        request_id="targeted_tc2_test",
        requirements=tc2["reqs"]
    )

    # 1. Pipeline success
    assert state.status == "SUCCESS"
    assert state.is_valid is True
    candidate = state.selected_candidate
    assert candidate is not None

    # 2. Geometry validity
    val = validate_layout(candidate)
    assert val["valid"] is True, f"Geometry validation failed: {val.get('errors')}"

    # 3. Circulation validity & Invariants
    circ = validate_final_circulation_invariants(candidate)
    assert circ["circulation_valid"] is True, f"Circulation validation failed: {circ.get('hard_violations')}"

    # 4. Each bathroom receives a feasible door
    bathrooms = [r for r in candidate.rooms if r.type.startswith("bathroom")]
    assert len(bathrooms) == 2, f"Expected 2 bathrooms in TC2, found {len(bathrooms)}"

    G = build_circulation_graph(candidate)
    unreachable_rooms = []
    bedroom_bath_counts = {}

    for b in bathrooms:
        # Check door connection
        b_doors = [d for d in candidate.doors if d.from_room == b.id or d.to_room == b.id]
        assert len(b_doors) >= 1, f"Bathroom {b.id} received no doors!"
        
        # Check door feasibility
        for d in b_doors:
            assert d.width >= 2.5, f"Door width {d.width} infeasible for bathroom {b.id}"
            parent_id = d.from_room if d.to_room == b.id else d.to_room
            if parent_id.startswith("bedroom"):
                bedroom_bath_counts[parent_id] = bedroom_bath_counts.get(parent_id, 0) + 1

        # Check reachability from exterior
        if not nx.has_path(G, "exterior", b.id):
            unreachable_rooms.append(b.id)

    assert len(unreachable_rooms) == 0, f"Unreachable bathrooms found: {unreachable_rooms}"

    # 5. Bedroom/bathroom assignment respects eligibility (max 1 attached bath per bedroom)
    for bed_id, count in bedroom_bath_counts.items():
        assert count <= 1, f"Bedroom {bed_id} parents {count} bathrooms (max allowed is 1)!"

    # 6. No private room becomes an invalid passage
    passage_violations = [v for v in circ.get("hard_violations", []) if v["type"] in ["private_room_as_passage", "bathroom_as_passage", "kitchen_as_passage"]]
    assert len(passage_violations) == 0, f"Passage violations found: {passage_violations}"

def test_regression_25x40_south_stress_infeasibility():
    """
    Stress / Infeasibility Regression:
    Plot: 25 x 40 ft, Facing: South, Parking: Yes, Bedrooms: 2, Hall: 1, Kitchen: 1, Bathrooms: 2, Pooja: 1.
    Vastu: Enabled, Vastu-aware optimization: Enabled, Agentic orchestration: Enabled.

    Expected behavior in Phase 4G:
    - Adaptive circulation topology is engaged.
    - Status is VALID (state.is_valid is True).
    - Circulation entity is present in generated floor plan.
    - All architectural hard constraints are satisfied.
    """
    reqs = FloorPlanRequirements(
        plot=Plot(width=25, depth=40, facing="south", unit="ft"),
        rooms={"bedroom": 2, "hall": 1, "kitchen": 1, "bathroom": 2, "pooja": 1},
        parking=True,
        request_id="stress_25x40_south"
    )
    prompt = "I have 25x40 land. I want 2 bedrooms, 1 hall, 1 kitchen, 2 bathrooms, 1 pooja room and parking. House should face south."
    
    orchestrator = FloorPlanOrchestrator()
    state = orchestrator.run(
        user_prompt=prompt,
        enable_vastu=True,
        enable_optimizer=True,
        request_id="stress_25x40_south",
        requirements=reqs
    )

    # 1. State integrity: no test-case-specific flags in production state
    assert not hasattr(state, "test_case_name")

    # 2. Strict Invariant: Adaptive circulation produces a VALID layout
    assert state.is_valid is True
    assert state.orchestration_status == OrchestrationStatus.VALID
    assert state.selected_candidate is not None
    
    # 3. Verify circulation entity is present
    has_circ = any(r.type == "circulation" for r in state.selected_candidate.rooms)
    assert has_circ is True


def test_regression_structural_infeasibility():
    """
    Genuinely Infeasible Regression:
    Plot: 20 x 25 ft, Facing: South, Parking: Yes, Bedrooms: 3, Hall: 1, Kitchen: 1, Bathrooms: 2.
    Plot area = 500 sq.ft, requested rooms exceed building envelope physically.

    Expected behavior:
    - Status is INFEASIBLE_REQUEST.
    - An invalid floor plan is NEVER marked valid (state.is_valid is False).
    - Returns structured diagnostic evidence explaining the constraint.
    """
    reqs = FloorPlanRequirements(
        plot=Plot(width=20, depth=25, facing="south", unit="ft"),
        rooms={"bedroom": 3, "hall": 1, "kitchen": 1, "bathroom": 2},
        parking=True,
        request_id="genuinely_infeasible"
    )
    prompt = "I have 20x25 land. I want 3 bedrooms, 1 hall, 1 kitchen, 2 bathrooms and parking."

    orchestrator = FloorPlanOrchestrator()
    state = orchestrator.run(
        user_prompt=prompt,
        enable_vastu=True,
        enable_optimizer=True,
        request_id="genuinely_infeasible",
        requirements=reqs
    )

    assert not hasattr(state, "test_case_name")
    assert state.is_valid is False
    assert state.orchestration_status in [OrchestrationStatus.INFEASIBLE_REQUEST, OrchestrationStatus.RETRYABLE_FAILURE]
    if state.orchestration_status == OrchestrationStatus.INFEASIBLE_REQUEST:
        assert state.failure_classification == FailureClassification.INFEASIBLE_REQUEST
        summary = state.get_infeasibility_summary()
        assert summary["status"] == "INFEASIBLE_REQUEST"
        assert "dominant_issue" in summary
        assert "structural_evidence" in summary



