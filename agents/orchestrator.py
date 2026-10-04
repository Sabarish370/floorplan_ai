import time
import uuid
from typing import Dict, Any, List, Optional, Tuple, Set
from agents.base import AgentIssue, AgentAction, AgentResult
from agents.state import (
    FloorPlanAgentState,
    AgentTraceStep,
    OrchestrationStatus,
    FailureClassification
)
from agents.requirements_agent import RequirementsAgent
from agents.layout_agent import LayoutAgent
from agents.architecture_agent import ArchitectureAgent
from agents.vastu_agent import VastuAgent
from agents.optimization_agent import OptimizationAgent
from agents.validation_agent import ValidationAgent

DIAGNOSIS_PRIORITY_ORDER = [
    # 1. Critical Geometry Failures (Highest Priority)
    "GEOMETRY_INVALID",
    "ROOM_OVERLAP",
    "OUTSIDE_PLOT_BOUNDARY",
    "INVALID_DIMENSIONS",
    "ENTRANCE_INVALID",
    
    # 2. Critical Circulation / Topology Failures
    "DISCONNECTED_ROOM",
    "PRIVATE_ROOM_AS_PASSAGE",
    "DOOR_INFEASIBLE",
    "CIRCULATION_VIOLATION",
    
    # 3. Architectural Warnings
    "ROOM_REALISM_VIOLATION",
    "DIRECT_ACCESS_VIOLATION",
    
    # 4. Space Efficiency Issues
    "LARGE_UNUSED_SPACE",
    "LOW_COMPACTNESS",
    "LOW_SPACE_UTILIZATION",
    
    # 5. Vastu Preferences (Lowest Priority among issues)
    "LOW_VASTU_SCORE",
    "VASTU_AVOID_ZONE",
]

HARD_STRUCTURAL_ISSUES = {
    "GEOMETRY_INVALID",
    "ROOM_OVERLAP",
    "OUTSIDE_PLOT_BOUNDARY",
    "INVALID_DIMENSIONS",
    "ENTRANCE_INVALID",
    "DISCONNECTED_ROOM",
    "PRIVATE_ROOM_AS_PASSAGE",
    "DOOR_INFEASIBLE",
    "CIRCULATION_VIOLATION",
}

DIAGNOSIS_ACTION_MAP = {
    # Geometry failures -> Layout retry
    "GEOMETRY_INVALID": "REGENERATE_LAYOUT",
    "ROOM_OVERLAP": "REGENERATE_LAYOUT",
    "OUTSIDE_PLOT_BOUNDARY": "REGENERATE_LAYOUT",
    "INVALID_DIMENSIONS": "REGENERATE_LAYOUT",
    "ENTRANCE_INVALID": "REGENERATE_LAYOUT",

    # Circulation failures -> Layout / topology retry
    "DISCONNECTED_ROOM": "REGENERATE_LAYOUT",
    "PRIVATE_ROOM_AS_PASSAGE": "REGENERATE_LAYOUT",
    "DOOR_INFEASIBLE": "REGENERATE_LAYOUT",
    "CIRCULATION_VIOLATION": "REGENERATE_LAYOUT",

    # Architectural warnings -> Layout retry or optimize
    "ROOM_REALISM_VIOLATION": "REGENERATE_LAYOUT",
    "DIRECT_ACCESS_VIOLATION": "REPACK_LAYOUT",

    # Space efficiency -> Deterministic packing/expansion
    "LARGE_UNUSED_SPACE": "REDUCE_UNUSED_SPACE",
    "LOW_COMPACTNESS": "REPACK_LAYOUT",
    "LOW_SPACE_UTILIZATION": "EXPAND_ROOMS",

    # Vastu preference -> Vastu optimization
    "LOW_VASTU_SCORE": "VASTU_OPTIMIZE",
    "VASTU_AVOID_ZONE": "VASTU_OPTIMIZE",

    # Valid plan
    "VALID_PLAN": "NO_ACTION"
}

class FloorPlanOrchestrator:
    """
    FloorPlanOrchestrator:
    Coordinates agent execution using explicit deterministic diagnosis -> action selection logic.
    
    NON-NEGOTIABLE ARCHITECTURAL PRINCIPLES:
    1. Does NOT use an LLM for diagnosis or flow control.
    2. Enforces strict priority:
         Geometry validity > Circulation validity > Architectural validity > Vastu preference > Space efficiency
    3. Production state contains NO test-case-specific concepts or hardcoded dimensions.
    4. Bounded execution with max 3 iterations; stops immediately on structural infeasibility.
    5. Final validation gate guarantees an invalid floor plan is NEVER marked valid or rendered.
    6. Distinguishes VALID, RETRYABLE_FAILURE, and INFEASIBLE_REQUEST using multi-factor structural evidence.
    7. Vastu preferences NEVER cause structural infeasibility.
    """
    def __init__(self):
        self.requirements_agent = RequirementsAgent()
        self.layout_agent = LayoutAgent()
        self.architecture_agent = ArchitectureAgent()
        self.vastu_agent = VastuAgent()
        self.optimization_agent = OptimizationAgent()
        self.validation_agent = ValidationAgent()

    def diagnose(self, state: FloorPlanAgentState) -> Tuple[str, str, Optional[AgentIssue]]:
        """
        Deterministic diagnosis:
        Scans state.active_issues in strict priority order and selects the next deterministic action.
        Returns: (dominant_issue_type, next_action, matching_issue)
        """
        # Prioritized scan
        for issue_type in DIAGNOSIS_PRIORITY_ORDER:
            matching = [i for i in state.active_issues if i.issue_type == issue_type]
            if matching:
                action = DIAGNOSIS_ACTION_MAP.get(issue_type, "NO_ACTION")
                return issue_type, action, matching[0]

        # Check if validation passed
        if state.is_valid:
            return "VALID_PLAN", "NO_ACTION", None
        else:
            return "GEOMETRY_INVALID", "REGENERATE_LAYOUT", None

    def classify_failure(
        self,
        state: FloorPlanAgentState,
        attempt_history: List[Dict[str, Any]]
    ) -> Tuple[FailureClassification, str, Dict[str, Any], List[str]]:
        """
        Conservative deterministic classification of generation failures:
        Distinguishes RETRYABLE_FAILURE from INFEASIBLE_REQUEST.
        
        PRINCIPLES:
        1. Never classifies infeasibility from retry count alone.
        2. Never uses hardcoded plot sizes or scenario names.
        3. Vastu preferences NEVER contribute to infeasibility.
        4. Infeasibility requires strong, multi-factor structural evidence:
           - Repeated structural invariant failures across multiple strategies
           - Complete candidate space exhaustion (zero complete valid candidates)
           - Persistent door/circulation or geometry bottleneck affecting specific room(s)
           - Zero circulation-valid and zero door-feasible candidates across attempts
        """
        attempts_count = len(attempt_history)
        if attempts_count == 0:
            return FailureClassification.RETRYABLE_FAILURE, "Initial attempt", {}, []

        last_attempt = attempt_history[-1]
        dominant_issue = last_attempt.get("dominant_issue", "UNKNOWN")
        affected_rooms = last_attempt.get("affected_rooms", [])

        # 1. Physical Capacity Check (Zero or Any Iteration)
        if state.requirements:
            reqs = state.requirements
            min_areas = {
                "bedroom": 100, "hall": 150, "kitchen": 60,
                "bathroom": 35, "pooja": 16, "dining": 60, "utility": 30
            }
            total_min_area = sum(min_areas.get(r.lower(), 50) * cnt for r, cnt in reqs.rooms.items())
            if reqs.parking:
                total_min_area += 140
            plot_area = reqs.plot.width * reqs.plot.depth
            if total_min_area > plot_area:
                evidence = {
                    "iterations_attempted": attempts_count,
                    "dominant_issue": "AREA_CAPACITY_EXCEEDED",
                    "affected_rooms": list(reqs.rooms.keys()),
                    "complete_candidates": 0,
                    "geometry_valid_candidates": 0,
                    "connectivity_valid_candidates": 0,
                    "circulation_valid_candidates": 0,
                    "door_feasible_candidates": 0,
                    "missing_requested_rooms": [],
                    "repeated_failure_count": attempts_count,
                    "search_strategy_information": [h.get("strategy", "unknown") for h in attempt_history],
                    "relevant_structural_constraint": "PLOT_AREA_CAPACITY",
                    "reasons": [
                        f"Total minimum required area ({total_min_area} sq.ft) exceeds available plot area ({plot_area} sq.ft)."
                    ]
                }
                relaxations = [
                    "Increase plot dimensions",
                    "Reduce number of requested rooms",
                    "Modify or remove parking requirement"
                ]
                return (
                    FailureClassification.INFEASIBLE_REQUEST,
                    f"Total minimum room area ({total_min_area} sq.ft) exceeds plot area ({plot_area} sq.ft).",
                    evidence,
                    relaxations
                )

        # 2. Multi-Attempt Conservative Structural Infeasibility Check
        # Rule: A single failure is ALWAYS retryable (could be transient seed/heuristic failure)
        if attempts_count < 2:
            evidence = {
                "iterations_attempted": attempts_count,
                "dominant_issue": dominant_issue,
                "affected_rooms": affected_rooms,
                "complete_candidates": last_attempt.get("complete_candidates", "unknown"),
                "geometry_valid_candidates": 1 if last_attempt.get("geometry_valid") else 0,
                "connectivity_valid_candidates": 1 if last_attempt.get("connectivity_valid") else 0,
                "circulation_valid_candidates": last_attempt.get("circulation_valid_count", 0),
                "door_feasible_candidates": last_attempt.get("door_feasible_count", 0),
                "missing_requested_rooms": last_attempt.get("missing_rooms", []),
                "repeated_failure_count": 1,
                "search_strategy_information": [h.get("strategy", "unknown") for h in attempt_history],
                "relevant_structural_constraint": "unknown",
                "reasons": ["Single attempt failed; retry with alternative layout strategy is recommended."]
            }
            return FailureClassification.RETRYABLE_FAILURE, f"Transient layout failure on attempt {attempts_count}.", evidence, []

        # When attempts >= 2: Evaluate multi-factor structural evidence
        # Factor A: All attempts must have failed on hard structural issues (Vastu excluded!)
        all_structural = all(h.get("dominant_issue") in HARD_STRUCTURAL_ISSUES for h in attempt_history)

        # Factor B: Candidate space structurally exhausted (0 complete candidates from beam search)
        zero_complete_candidates = all(h.get("complete_candidates", 0) == 0 for h in attempt_history)

        # Factor C: Persistent room or topological bottleneck across attempts
        room_sets = [set(h.get("affected_rooms", [])) for h in attempt_history if h.get("affected_rooms")]
        persistent_rooms = set.intersection(*room_sets) if room_sets else set()

        # Factor D: Circulation and Door Feasibility exhausted across all generated candidates
        zero_circ_valid = all(h.get("circulation_valid_count", 0) == 0 for h in attempt_history)
        zero_door_feasible = all(h.get("door_feasible_count", 0) == 0 for h in attempt_history)

        # Same dominant issue across attempts
        same_dominant_issue = len(set(h.get("dominant_issue") for h in attempt_history)) == 1

        if all_structural and zero_complete_candidates and zero_circ_valid and zero_door_feasible and (persistent_rooms or same_dominant_issue):
            target_rooms_list = sorted(list(persistent_rooms)) if persistent_rooms else affected_rooms
            rooms_str = f" for room(s) {', '.join(target_rooms_list)}" if target_rooms_list else ""
            
            constraint_name = "CIRCULATION_AND_DOOR_CONNECTIVITY" if dominant_issue in ["DISCONNECTED_ROOM", "DOOR_INFEASIBLE", "CIRCULATION_VIOLATION"] else "BOUNDARY_AND_GEOMETRY"

            evidence = {
                "iterations_attempted": attempts_count,
                "dominant_issue": dominant_issue,
                "affected_rooms": target_rooms_list,
                "complete_candidates": 0,
                "geometry_valid_candidates": sum(1 if h.get("geometry_valid", False) else 0 for h in attempt_history),
                "connectivity_valid_candidates": sum(1 if h.get("connectivity_valid", False) else 0 for h in attempt_history),
                "circulation_valid_candidates": 0,
                "door_feasible_candidates": 0,
                "missing_requested_rooms": [r for h in attempt_history for r in h.get("missing_rooms", [])],
                "repeated_failure_count": attempts_count,
                "search_strategy_information": [h.get("strategy", "unknown") for h in attempt_history],
                "relevant_structural_constraint": constraint_name,
                "reasons": [
                    f"Candidate space structurally exhausted across {attempts_count} generation strategies with zero complete valid candidates.",
                    f"Persistent {dominant_issue}{rooms_str} under current plot and room geometry.",
                    "Zero door-feasible and circulation-valid candidate layouts could be constructed."
                ]
            }

            relaxations = [
                "Increase plot size (width or depth) to provide additional access perimeter",
                "Reduce the number of requested rooms",
                "Modify or remove parking requirement to free frontage for room connectivity",
                "Relax architectural direct-access constraints if permissible"
            ]

            reason = f"No valid floor plan was found under current system constraints due to persistent {dominant_issue}{rooms_str}."
            return FailureClassification.INFEASIBLE_REQUEST, reason, evidence, relaxations

        # Fallback: Retryable failure
        evidence = {
            "iterations_attempted": attempts_count,
            "dominant_issue": dominant_issue,
            "affected_rooms": affected_rooms,
            "complete_candidates": sum(h.get("complete_candidates", 0) for h in attempt_history),
            "geometry_valid_candidates": sum(1 if h.get("geometry_valid", False) else 0 for h in attempt_history),
            "connectivity_valid_candidates": sum(1 if h.get("connectivity_valid", False) else 0 for h in attempt_history),
            "circulation_valid_candidates": sum(h.get("circulation_valid_count", 0) for h in attempt_history),
            "door_feasible_candidates": sum(h.get("door_feasible_count", 0) for h in attempt_history),
            "missing_requested_rooms": [r for h in attempt_history for r in h.get("missing_rooms", [])],
            "repeated_failure_count": attempts_count,
            "search_strategy_information": [h.get("strategy", "unknown") for h in attempt_history],
            "relevant_structural_constraint": "unknown",
            "reasons": ["Generation failure does not meet conservative structural infeasibility criteria; remains retryable."]
        }
        return FailureClassification.RETRYABLE_FAILURE, f"Retryable generation failure on attempt {attempts_count}.", evidence, []

    def _record_trace(self, state: FloorPlanAgentState, agent_name: str, result: AgentResult):
        step = AgentTraceStep(
            agent_name=agent_name,
            iteration=state.iteration,
            status=result.status,
            action_taken=result.recommended_action,
            duration_ms=result.duration_ms,
            message=f"Status: {result.status}. Recommended action: {result.recommended_action}. Issues: {len(result.issues)}"
        )
        state.trace.append(step)

    def run(self, user_prompt: str, enable_vastu: bool = True, enable_optimizer: bool = True, request_id: Optional[str] = None, requirements: Optional[Any] = None) -> FloorPlanAgentState:
        """
        Executes the agentic orchestration lifecycle for a real user request.
        """
        req_id = request_id or uuid.uuid4().hex[:8]
        state = FloorPlanAgentState(
            request_id=req_id,
            user_prompt=user_prompt,
            requirements=requirements,
            enable_vastu=enable_vastu,
            enable_optimizer=enable_optimizer,
            max_iterations=3,
            status="INITIALIZING",
            orchestration_status=OrchestrationStatus.INITIALIZING,
            failure_classification=FailureClassification.NONE
        )

        # Step 1: Requirements Extraction (Single Gemini call)
        req_res = self.requirements_agent.run(state)
        self._record_trace(state, self.requirements_agent.name, req_res)
        
        if req_res.status == "FAIL" or not state.requirements:
            state.status = "FAILED"
            state.orchestration_status = OrchestrationStatus.FAILED
            state.failure_classification = FailureClassification.NONE
            state.error_message = req_res.metrics.get("error", "Requirements extraction failed.")
            return state

        state.status = "REQUIREMENTS_PARSED"
        state.orchestration_status = OrchestrationStatus.REQUIREMENTS_PARSED

        # Alternative strategies for bounded layout retry
        retry_strategies = ["vastu_first", "kitchen_first", "bedroom_first", "balanced", "baseline"]
        attempt_history: List[Dict[str, Any]] = []

        # Step 2: Bounded Iteration Loop (Max 3 iterations)
        while state.iteration < state.max_iterations:
            current_iter = state.iteration
            
            # Select strategy for this attempt
            state.preferred_strategy = retry_strategies[min(current_iter, len(retry_strategies) - 1)]
            state.active_issues = []  # Reset active issues for fresh candidate evaluation

            # 2a. Layout Generation
            layout_res = self.layout_agent.run(state)
            self._record_trace(state, self.layout_agent.name, layout_res)
            
            if layout_res.status == "FAIL" or state.selected_candidate is None:
                attempt_record = {
                    "iteration": current_iter,
                    "strategy": state.preferred_strategy,
                    "dominant_issue": "NO_LAYOUT_CANDIDATE",
                    "affected_rooms": [],
                    "layout_metrics": layout_res.metrics if layout_res else {},
                    "complete_candidates": 0,
                    "circulation_valid_count": 0,
                    "door_feasible_count": 0,
                    "geometry_valid": False,
                    "connectivity_valid": False,
                    "missing_rooms": [],
                    "is_valid": False
                }
                attempt_history.append(attempt_record)
                
                classification, reason, evidence, relaxations = self.classify_failure(state, attempt_history)
                if classification == FailureClassification.INFEASIBLE_REQUEST:
                    state.failure_classification = FailureClassification.INFEASIBLE_REQUEST
                    state.orchestration_status = OrchestrationStatus.INFEASIBLE_REQUEST
                    state.status = "INFEASIBLE_REQUEST"
                    state.is_valid = False
                    state.retry_recommended = False
                    state.diagnosis_reason = reason
                    state.affected_rooms = evidence.get("affected_rooms", [])
                    state.structural_evidence = evidence
                    state.infeasibility_reasons = evidence.get("reasons", [reason])
                    state.recommended_relaxations = relaxations
                    state.attempted_iterations = current_iter + 1
                    state.error_message = reason
                    break
                else:
                    if current_iter + 1 < state.max_iterations:
                        state.iteration += 1
                        continue
                    else:
                        state.status = "FAILED"
                        state.orchestration_status = OrchestrationStatus.FAILED
                        state.failure_classification = FailureClassification.RETRYABLE_FAILURE
                        state.attempted_iterations = current_iter + 1
                        state.error_message = "Layout generation failed within retry budget."
                        break

            # 2b. Architecture & Circulation Evaluation (calls deterministic doors engine)
            arch_res = self.architecture_agent.run(state)
            self._record_trace(state, self.architecture_agent.name, arch_res)

            # 2c. Validation Gate
            val_res = self.validation_agent.run(state)
            self._record_trace(state, self.validation_agent.name, val_res)

            # 2d. Flow Branching based on Validation Result:
            if state.is_valid:
                # CANDIDATE IS VALID
                # Now evaluate Vastu preferences
                if state.enable_vastu:
                    vastu_res = self.vastu_agent.run(state)
                    self._record_trace(state, self.vastu_agent.name, vastu_res)

                # Deterministic Diagnosis -> Action Selection
                dominant_issue, next_action, matching_issue = self.diagnose(state)
                state.action_history.append(AgentAction(
                    action_type=next_action,
                    target=dominant_issue,
                    reason=f"Diagnosed issue '{dominant_issue}' on iteration {current_iter}."
                ))

                if next_action == "NO_ACTION":
                    state.status = "SUCCESS"
                    state.orchestration_status = OrchestrationStatus.VALID
                    state.failure_classification = FailureClassification.NONE
                    state.attempted_iterations = current_iter + 1
                    state.is_valid = True
                    break

                elif next_action in ["REDUCE_UNUSED_SPACE", "REPACK_LAYOUT", "EXPAND_ROOMS", "VASTU_OPTIMIZE"]:
                    if state.enable_optimizer:
                        state.status = "OPTIMIZING"
                        opt_res = self.optimization_agent.run(state)
                        self._record_trace(state, self.optimization_agent.name, opt_res)

                        arch_res_after = self.architecture_agent.run(state)
                        self._record_trace(state, self.architecture_agent.name, arch_res_after)

                        val_res_after = self.validation_agent.run(state)
                        self._record_trace(state, self.validation_agent.name, val_res_after)

                        if state.enable_vastu:
                            vastu_res_after = self.vastu_agent.run(state)
                            self._record_trace(state, self.vastu_agent.name, vastu_res_after)

                        if state.is_valid:
                            state.status = "SUCCESS"
                            state.orchestration_status = OrchestrationStatus.VALID
                            state.failure_classification = FailureClassification.NONE
                            state.attempted_iterations = current_iter + 1
                            break
                        else:
                            pass
                    else:
                        state.status = "SUCCESS"
                        state.orchestration_status = OrchestrationStatus.VALID
                        state.failure_classification = FailureClassification.NONE
                        state.attempted_iterations = current_iter + 1
                        break

            # If here: state.is_valid is False (hard structural failure)
            # As per architectural principle: DO NOT run Vastu optimization on a hard structural failure.
            dominant_issue, next_action, matching_issue = self.diagnose(state)
            crit_issues = [i for i in state.active_issues if i.severity == "CRITICAL"]
            affected_rooms = [i.target for i in crit_issues if i.target]

            layout_metrics = layout_res.metrics if layout_res else {}
            complete_cands = layout_metrics.get("complete_candidates", 0)
            if any(iss.issue_type == "BEAM_SEARCH_FALLBACK" for iss in state.active_issues):
                complete_cands = 0

            cand = state.selected_candidate
            circ_valid_cnt = 0
            door_feas_cnt = 0
            geo_valid = False
            conn_valid = False
            missing_rms = []

            if cand:
                if not any(i.issue_type in ["GEOMETRY_INVALID", "ROOM_OVERLAP", "OUTSIDE_PLOT_BOUNDARY"] for i in crit_issues):
                    geo_valid = True
                if not any(i.issue_type in ["DISCONNECTED_ROOM", "DOOR_INFEASIBLE"] for i in crit_issues):
                    conn_valid = True
                    circ_valid_cnt = 1
                    door_feas_cnt = 1
                if state.requirements:
                    req_count = sum(state.requirements.rooms.values())
                    placed_count = len([r for r in cand.rooms if r.type != 'parking'])
                    if placed_count < req_count:
                        missing_rms = [f"missing_{req_count - placed_count}_rooms"]

            attempt_record = {
                "iteration": current_iter,
                "strategy": state.preferred_strategy,
                "dominant_issue": dominant_issue,
                "affected_rooms": affected_rooms,
                "layout_metrics": layout_metrics,
                "complete_candidates": complete_cands,
                "circulation_valid_count": circ_valid_cnt,
                "door_feasible_count": door_feas_cnt,
                "geometry_valid": geo_valid,
                "connectivity_valid": conn_valid,
                "missing_rooms": missing_rms,
                "active_issues": [i.issue_type for i in state.active_issues],
                "critical_issues": [i.issue_type for i in crit_issues],
                "is_valid": False
            }
            attempt_history.append(attempt_record)

            # Deterministic Classification: RETRYABLE vs INFEASIBLE_REQUEST
            classification, reason, evidence, relaxations = self.classify_failure(state, attempt_history)
            
            state.action_history.append(AgentAction(
                action_type="CLASSIFY_FAILURE",
                target=classification.value,
                reason=reason
            ))

            if classification == FailureClassification.INFEASIBLE_REQUEST:
                # STOP RETRIES IMMEDIATELY! Do not retry, do not optimize, do not render.
                state.failure_classification = FailureClassification.INFEASIBLE_REQUEST
                state.orchestration_status = OrchestrationStatus.INFEASIBLE_REQUEST
                state.status = "INFEASIBLE_REQUEST"
                state.is_valid = False
                state.retry_recommended = False
                state.diagnosis_reason = reason
                state.affected_rooms = evidence.get("affected_rooms", affected_rooms)
                state.structural_evidence = evidence
                state.infeasibility_reasons = evidence.get("reasons", [reason])
                state.recommended_relaxations = relaxations
                state.attempted_iterations = current_iter + 1
                state.error_message = reason
                break
            else:
                # Retryable failure
                state.failure_classification = FailureClassification.RETRYABLE_FAILURE
                state.orchestration_status = OrchestrationStatus.RETRYABLE_FAILURE
                state.retry_recommended = True
                state.diagnosis_reason = reason
                state.affected_rooms = affected_rooms
                state.structural_evidence = evidence
                state.attempted_iterations = current_iter + 1
                
                if current_iter + 1 < state.max_iterations:
                    state.iteration += 1
                    continue
                else:
                    # Retry budget exhausted
                    state.status = "FAILED"
                    state.orchestration_status = OrchestrationStatus.FAILED
                    state.is_valid = False
                    state.error_message = f"Generation could not produce a valid floor plan within retry budget ({state.max_iterations} attempts). Last issue: {dominant_issue}."
                    break

        # Step 3: Strict Quality Gate
        if state.orchestration_status == OrchestrationStatus.INFEASIBLE_REQUEST:
            state.is_valid = False
        elif state.selected_candidate is not None and state.is_valid:
            final_val = self.validation_agent.run(state)
            self._record_trace(state, self.validation_agent.name, final_val)
            if not state.is_valid:
                state.status = "FAILED"
                state.orchestration_status = OrchestrationStatus.FAILED
                if not state.error_message:
                    crit_msgs = [i.message for i in state.active_issues if i.severity == "CRITICAL"]
                    state.error_message = "; ".join(crit_msgs) if crit_msgs else "Layout failed final validation."
            else:
                state.status = "SUCCESS"
                state.orchestration_status = OrchestrationStatus.VALID

        return state
