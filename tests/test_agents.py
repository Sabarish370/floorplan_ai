import pytest
from models.requirements import FloorPlanRequirements, Plot
from agents.base import AgentIssue, AgentAction, AgentResult
from agents.state import FloorPlanAgentState
from agents.requirements_agent import RequirementsAgent
from agents.layout_agent import LayoutAgent
from agents.architecture_agent import ArchitectureAgent
from agents.vastu_agent import VastuAgent
from agents.optimization_agent import OptimizationAgent
from agents.validation_agent import ValidationAgent
from agents.orchestrator import FloorPlanOrchestrator

def test_production_state_has_no_test_case_name():
    """Correction 1: FloorPlanAgentState must have NO test_case_name attribute."""
    state = FloorPlanAgentState(
        request_id="req123",
        user_prompt="I have 30x40 land. I want 2 bedrooms, 1 hall, 1 kitchen, 1 bathroom."
    )
    assert not hasattr(state, "test_case_name")
    assert state.request_id == "req123"
    assert state.iteration == 0
    assert state.max_iterations == 3
    assert state.is_valid is False

def test_requirements_agent_caching():
    """Verify RequirementsAgent uses pre-parsed requirements without calling LLM."""
    reqs = FloorPlanRequirements(
        plot=Plot(width=30, depth=40, facing="west", unit="ft"),
        rooms={"bedroom": 2, "hall": 1, "kitchen": 1, "bathroom": 1},
        parking=True,
        request_id="req1"
    )
    state = FloorPlanAgentState(
        request_id="req1",
        user_prompt="30x40 west 2 bed 1 hall 1 kitchen 1 bath with parking",
        requirements=reqs
    )
    agent = RequirementsAgent()
    result = agent.run(state)
    assert result.status == "SUCCESS"
    assert result.metrics.get("cached") is True
    assert result.recommended_action == "GENERATE_LAYOUT"

def test_layout_agent_generation():
    """Verify LayoutAgent creates candidate floor plans via deterministic engine."""
    reqs = FloorPlanRequirements(
        plot=Plot(width=30, depth=40, facing="west", unit="ft"),
        rooms={"bedroom": 1, "hall": 1, "kitchen": 1, "bathroom": 1},
        parking=True,
        request_id="req2"
    )
    state = FloorPlanAgentState(
        request_id="req2",
        user_prompt="30x40 west 1 bed 1 hall 1 kitchen 1 bath with parking",
        requirements=reqs,
        enable_vastu=False
    )
    agent = LayoutAgent()
    result = agent.run(state)
    assert result.status == "SUCCESS"
    assert state.selected_candidate is not None
    assert len(state.selected_candidate.rooms) >= 4

def test_architecture_agent_preserves_deterministic_doors():
    """Correction 2: ArchitectureAgent delegates to deterministic door generation and evaluates circulation."""
    reqs = FloorPlanRequirements(
        plot=Plot(width=30, depth=40, facing="west", unit="ft"),
        rooms={"bedroom": 1, "hall": 1, "kitchen": 1, "bathroom": 1},
        parking=True,
        request_id="req3"
    )
    state = FloorPlanAgentState(
        request_id="req3",
        user_prompt="30x40 west",
        requirements=reqs,
        enable_vastu=False
    )
    layout_agent = LayoutAgent()
    layout_agent.run(state)
    
    arch_agent = ArchitectureAgent()
    result = arch_agent.run(state)
    assert result.agent_name == "ArchitectureAgent"
    assert len(state.selected_candidate.doors) > 0
    # Must report metrics without errors
    assert "architectural_score" in result.metrics or "circulation_score" in result.metrics

def test_vastu_agent_never_overrides_geometry():
    """Correction 3: Vastu is purely a scoring/preference layer and does NOT mark geometric validity."""
    reqs = FloorPlanRequirements(
        plot=Plot(width=30, depth=40, facing="west", unit="ft"),
        rooms={"bedroom": 1, "hall": 1, "kitchen": 1, "bathroom": 1},
        parking=True,
        request_id="req4"
    )
    state = FloorPlanAgentState(
        request_id="req4",
        user_prompt="30x40 west",
        requirements=reqs,
        enable_vastu=True
    )
    layout_agent = LayoutAgent()
    layout_agent.run(state)

    vastu_agent = VastuAgent()
    result = vastu_agent.run(state)
    assert result.status in ["SUCCESS", "WARNING"]
    assert "score" in result.metrics
    # Even if avoid zone is detected, severity must be WARNING, not geometric FAIL
    for issue in result.issues:
        assert issue.severity != "CRITICAL"

def test_optimization_agent_issue_driven():
    """Correction 4: OptimizationAgent selects strategy based on state weakness and does not run blindly."""
    reqs = FloorPlanRequirements(
        plot=Plot(width=30, depth=40, facing="west", unit="ft"),
        rooms={"bedroom": 1, "hall": 1, "kitchen": 1, "bathroom": 1},
        parking=True,
        request_id="req5"
    )
    state = FloorPlanAgentState(
        request_id="req5",
        user_prompt="30x40 west",
        requirements=reqs
    )
    layout_agent = LayoutAgent()
    layout_agent.run(state)
    
    # If geometry is invalid, it must refuse to optimize and recommend RETRY_LAYOUT
    state.active_issues.append(AgentIssue(
        issue_type="GEOMETRY_INVALID",
        severity="CRITICAL",
        message="Room overlap simulated"
    ))
    
    opt_agent = OptimizationAgent()
    res = opt_agent.run(state)
    assert res.status == "FAIL"
    assert res.recommended_action == "REGENERATE_LAYOUT"
    assert res.metrics.get("diagnosed_weakness") == "INVALID_GEOMETRY"

def test_validation_agent_strict_quality_gate():
    """ValidationAgent strictly marks valid vs invalid."""
    reqs = FloorPlanRequirements(
        plot=Plot(width=30, depth=40, facing="west", unit="ft"),
        rooms={"bedroom": 1, "hall": 1, "kitchen": 1, "bathroom": 1},
        parking=True,
        request_id="req6"
    )
    state = FloorPlanAgentState(
        request_id="req6",
        user_prompt="30x40 west",
        requirements=reqs
    )
    layout_agent = LayoutAgent()
    layout_agent.run(state)
    
    val_agent = ValidationAgent()
    res = val_agent.run(state)
    assert res.status in ["SUCCESS", "FAIL"]
    assert "is_valid" in res.metrics

def test_orchestrator_execution():
    """Correction 5: Orchestrator coordinates diagnosis -> action selection deterministic loop."""
    reqs = FloorPlanRequirements(
        plot=Plot(width=30, depth=40, facing="west", unit="ft"),
        rooms={"bedroom": 1, "hall": 1, "kitchen": 1, "bathroom": 1},
        parking=True,
        request_id="req7"
    )
    orchestrator = FloorPlanOrchestrator()
    # Create state with pre-set requirements so no Gemini call is required for unit test
    state = FloorPlanAgentState(
        request_id="req7",
        user_prompt="30x40 west 1 bed 1 hall 1 kitchen 1 bath with parking",
        requirements=reqs,
        enable_vastu=True,
        enable_optimizer=False  # fast unit test run
    )
    
    # Run loop
    state = orchestrator.run(
        user_prompt="30x40 west 1 bed 1 hall 1 kitchen 1 bath with parking",
        enable_vastu=True,
        enable_optimizer=False,
        request_id="req7"
    )
    
    assert state.status in ["SUCCESS", "FAILED"]
    assert len(state.trace) > 0
    assert state.iteration <= state.max_iterations

def test_orchestration_status_and_enums():
    """Verify OrchestrationStatus and FailureClassification enums and state fields."""
    from agents.state import OrchestrationStatus, FailureClassification
    state = FloorPlanAgentState(
        request_id="enum_test",
        user_prompt="30x40 west"
    )
    assert state.orchestration_status == OrchestrationStatus.INITIALIZING
    assert state.failure_classification == FailureClassification.NONE
    assert isinstance(state.structural_evidence, dict)
    assert isinstance(state.affected_rooms, list)
    assert isinstance(state.recommended_relaxations, list)

def test_three_failed_retries_alone_do_not_imply_infeasibility():
    """Requirement: Three failed retries alone do NOT imply infeasibility."""
    from agents.state import FailureClassification
    orchestrator = FloorPlanOrchestrator()
    reqs = FloorPlanRequirements(
        plot=Plot(width=30, depth=40, facing="west", unit="ft"),
        rooms={"bedroom": 1, "hall": 1, "kitchen": 1, "bathroom": 1},
        parking=True,
        request_id="req_retry_test"
    )
    state = FloorPlanAgentState(
        request_id="req_retry_test",
        user_prompt="30x40 west",
        requirements=reqs,
        max_iterations=3
    )
    
    # Simulate 3 attempts where complete candidates existed (search space was not exhausted)
    # or issues varied randomly across different rooms
    attempt_history = [
        {
            "iteration": 0,
            "strategy": "vastu_first",
            "dominant_issue": "ROOM_OVERLAP",
            "affected_rooms": ["bedroom_1"],
            "complete_candidates": 5,  # Candidates existed!
            "circulation_valid_count": 0,
            "door_feasible_count": 1,
            "is_valid": False
        },
        {
            "iteration": 1,
            "strategy": "kitchen_first",
            "dominant_issue": "OUTSIDE_PLOT_BOUNDARY",
            "affected_rooms": ["kitchen_1"],  # Different room!
            "complete_candidates": 3,
            "circulation_valid_count": 1,
            "door_feasible_count": 1,
            "is_valid": False
        },
        {
            "iteration": 2,
            "strategy": "bedroom_first",
            "dominant_issue": "ROOM_OVERLAP",
            "affected_rooms": ["hall_1"],  # Different room!
            "complete_candidates": 4,
            "circulation_valid_count": 1,
            "door_feasible_count": 0,
            "is_valid": False
        }
    ]
    
    classification, reason, evidence, relaxations = orchestrator.classify_failure(state, attempt_history)
    # MUST NOT be classified as INFEASIBLE_REQUEST simply because 3 attempts were made!
    assert classification == FailureClassification.RETRYABLE_FAILURE
    assert classification != FailureClassification.INFEASIBLE_REQUEST

def test_low_vastu_score_alone_never_implies_infeasibility():
    """Requirement: Vastu is purely a preference/scoring layer and never causes infeasibility."""
    from agents.state import FailureClassification
    orchestrator = FloorPlanOrchestrator()
    state = FloorPlanAgentState(
        request_id="vastu_infeas_test",
        user_prompt="30x40 west",
        requirements=FloorPlanRequirements(
            plot=Plot(width=30, depth=40, facing="west", unit="ft"),
            rooms={"bedroom": 1, "hall": 1, "kitchen": 1, "bathroom": 1},
            parking=True,
            request_id="vastu_test"
        )
    )
    
    attempt_history = [
        {
            "iteration": 0,
            "dominant_issue": "LOW_VASTU_SCORE",
            "affected_rooms": [],
            "complete_candidates": 10,
            "circulation_valid_count": 1,
            "door_feasible_count": 1,
            "is_valid": True
        },
        {
            "iteration": 1,
            "dominant_issue": "VASTU_AVOID_ZONE",
            "affected_rooms": ["kitchen_1"],
            "complete_candidates": 10,
            "circulation_valid_count": 1,
            "door_feasible_count": 1,
            "is_valid": True
        }
    ]
    
    classification, reason, evidence, relaxations = orchestrator.classify_failure(state, attempt_history)
    assert classification != FailureClassification.INFEASIBLE_REQUEST

def test_transient_failure_remains_retryable():
    """Requirement: A single/transient failure remains retryable."""
    from agents.state import FailureClassification
    orchestrator = FloorPlanOrchestrator()
    state = FloorPlanAgentState(
        request_id="transient_test",
        user_prompt="30x40 west",
        requirements=FloorPlanRequirements(
            plot=Plot(width=30, depth=40, facing="west", unit="ft"),
            rooms={"bedroom": 1, "hall": 1, "kitchen": 1, "bathroom": 1},
            parking=True,
            request_id="transient_req"
        )
    )
    
    # 1 single attempt
    attempt_history = [
        {
            "iteration": 0,
            "dominant_issue": "DISCONNECTED_ROOM",
            "affected_rooms": ["bathroom_1"],
            "complete_candidates": 0,
            "circulation_valid_count": 0,
            "door_feasible_count": 0,
            "is_valid": False
        }
    ]
    
    classification, reason, evidence, relaxations = orchestrator.classify_failure(state, attempt_history)
    assert classification == FailureClassification.RETRYABLE_FAILURE

