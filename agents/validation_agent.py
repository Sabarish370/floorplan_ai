import time
from typing import Dict, Any, List
from agents.base import BaseAgent, AgentResult, AgentIssue, AgentAction
from agents.state import FloorPlanAgentState
from layout.validator import validate_layout
from layout.architecture import validate_final_circulation_invariants

class ValidationAgent(BaseAgent):
    """
    ValidationAgent:
    Acts as the final, independent quality gate.
    Wraps layout.validator.validate_layout and layout.architecture.validate_final_circulation_invariants.
    
    Guarantees:
    - Checks boundary containment, room overlaps, dimensions, entrance orientation.
    - Checks graph reachability and private room passage invariants.
    - Sets state.is_valid = True ONLY when all hard constraints pass.
    - An invalid plan is NEVER marked valid.
    """
    name: str = "ValidationAgent"

    def run(self, state: FloorPlanAgentState) -> AgentResult:
        t0 = time.time()
        issues: List[AgentIssue] = []
        actions: List[AgentAction] = []

        if state.selected_candidate is None:
            state.is_valid = False
            res = AgentResult(
                agent_name=self.name,
                status="FAIL",
                issues=[AgentIssue(
                    issue_type="NO_LAYOUT_CANDIDATE",
                    severity="CRITICAL",
                    message="ValidationAgent requires a candidate floor plan to validate."
                )],
                recommended_action="REGENERATE_LAYOUT",
                duration_ms=0.0
            )
            state.validation_result = res
            return res

        candidate = state.selected_candidate
        
        # 1. Authoritative Layout Geometry Validation
        val_res = validate_layout(candidate)
        for err in val_res.get("errors", []):
            err_lower = err.lower()
            if "overlap" in err_lower:
                issue_type = "ROOM_OVERLAP"
            elif "outside" in err_lower or "boundary" in err_lower:
                issue_type = "OUTSIDE_PLOT_BOUNDARY"
            elif "dimension" in err_lower:
                issue_type = "INVALID_DIMENSIONS"
            elif "entrance" in err_lower or "gate" in err_lower:
                issue_type = "ENTRANCE_INVALID"
            elif "accessible" in err_lower or "isolated" in err_lower:
                issue_type = "DISCONNECTED_ROOM"
            else:
                issue_type = "GEOMETRY_INVALID"

            issues.append(AgentIssue(
                issue_type=issue_type,
                severity="CRITICAL",
                message=err
            ))

        for warn in val_res.get("warnings", []):
            issues.append(AgentIssue(
                issue_type="LAYOUT_WARNING",
                severity="WARNING",
                message=warn
            ))

        # 2. Circulation Invariants Validation
        circ_res = validate_final_circulation_invariants(candidate)
        if not circ_res.get("circulation_valid", True):
            for viol in circ_res.get("hard_violations", []):
                v_type = viol.get("type", "")
                if v_type == "unreachable_room":
                    issues.append(AgentIssue(
                        issue_type="DISCONNECTED_ROOM",
                        target=viol.get("room"),
                        severity="CRITICAL",
                        message=f"Circulation Invariant: Room '{viol.get('room')}' cannot be reached."
                    ))
                elif "passage" in v_type:
                    issues.append(AgentIssue(
                        issue_type="PRIVATE_ROOM_AS_PASSAGE",
                        target=viol.get("passage_room"),
                        severity="CRITICAL",
                        message=f"Circulation Invariant: '{viol.get('passage_room')}' is a forbidden passage room for {viol.get('dependent_rooms')}."
                    ))
                else:
                    issues.append(AgentIssue(
                        issue_type="CIRCULATION_VIOLATION",
                        severity="CRITICAL",
                        message=f"Circulation Invariant failed: {viol}"
                    ))

        # 3. Final Gate Evaluation
        critical_issues = [i for i in issues if i.severity == "CRITICAL"]
        is_plan_valid = (len(critical_issues) == 0) and val_res.get("valid", False) and circ_res.get("circulation_valid", False)
        
        state.is_valid = is_plan_valid
        
        if is_plan_valid:
            status = "SUCCESS"
            recommended_action = "NO_ACTION"
        else:
            status = "FAIL"
            # Explicit deterministic recommendation mapping
            if any(i.issue_type in ["GEOMETRY_INVALID", "ROOM_OVERLAP", "OUTSIDE_PLOT_BOUNDARY"] for i in critical_issues):
                recommended_action = "REGENERATE_LAYOUT"
            elif any(i.issue_type == "DISCONNECTED_ROOM" for i in critical_issues):
                recommended_action = "REGENERATE_LAYOUT"
            elif any(i.issue_type == "PRIVATE_ROOM_AS_PASSAGE" for i in critical_issues):
                recommended_action = "REGENERATE_LAYOUT"
            elif any(i.issue_type == "DOOR_INFEASIBLE" for i in critical_issues):
                recommended_action = "REGENERATE_LAYOUT"
            else:
                recommended_action = "REGENERATE_LAYOUT"

        metrics = val_res.get("metrics", {})
        metrics["is_valid"] = is_plan_valid
        metrics["critical_issues_count"] = len(critical_issues)
        metrics["warning_issues_count"] = len([i for i in issues if i.severity == "WARNING"])

        duration = (time.time() - t0) * 1000
        res = AgentResult(
            agent_name=self.name,
            status=status,
            issues=issues,
            recommended_action=recommended_action,
            metrics=metrics,
            actions=actions,
            duration_ms=round(duration, 2)
        )
        state.validation_result = res
        
        for iss in issues:
            if not any(e.issue_type == iss.issue_type and e.target == iss.target for e in state.active_issues):
                state.active_issues.append(iss)
                
        return res
