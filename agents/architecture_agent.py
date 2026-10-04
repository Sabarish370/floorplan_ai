import time
from typing import Dict, Any, List
from agents.base import BaseAgent, AgentResult, AgentIssue, AgentAction
from agents.state import FloorPlanAgentState
from layout.doors import generate_internal_doors
from layout.architecture import (
    validate_circulation_constraints,
    evaluate_architecture,
    validate_final_circulation_invariants,
    build_circulation_graph
)

class ArchitectureAgent(BaseAgent):
    """
    ArchitectureAgent:
    Evaluates circulation, reachability, direct Hall access, private-room-as-passage violations,
    and door feasibility.
    
    CRITICAL: Does NOT duplicate or replace the deterministic door-generation engine (layout/doors.py).
    Delegates to layout.doors.generate_internal_doors when door generation or refresh is needed.
    """
    name: str = "ArchitectureAgent"

    def run(self, state: FloorPlanAgentState) -> AgentResult:
        t0 = time.time()
        issues: List[AgentIssue] = []
        actions: List[AgentAction] = []
        
        if state.selected_candidate is None:
            res = AgentResult(
                agent_name=self.name,
                status="FAIL",
                issues=[AgentIssue(
                    issue_type="NO_LAYOUT_CANDIDATE",
                    severity="CRITICAL",
                    message="ArchitectureAgent requires a selected layout candidate."
                )],
                recommended_action="REGENERATE_LAYOUT",
                duration_ms=0.0
            )
            state.architecture_result = res
            return res

        candidate = state.selected_candidate

        # 1. Authoritative Door Generation / Check
        # If doors are missing or empty, call the authoritative existing deterministic engine
        if not candidate.doors:
            try:
                candidate.doors = generate_internal_doors([r.model_dump() for r in candidate.rooms])
                actions.append(AgentAction(
                    action_type="GENERATE_INTERNAL_DOORS",
                    reason="Doors were unpopulated; generated using layout.doors engine."
                ))
            except Exception as e:
                issues.append(AgentIssue(
                    issue_type="DOOR_INFEASIBLE",
                    severity="CRITICAL",
                    message=f"Door generation failed: {str(e)}"
                ))

        # 2. Check Door Feasibility per room
        rooms_with_doors = set()
        for d in candidate.doors:
            rooms_with_doors.add(d.from_room)
            rooms_with_doors.add(d.to_room)
            
        for room in candidate.rooms:
            if room.type != 'parking' and room.id not in rooms_with_doors:
                issues.append(AgentIssue(
                    issue_type="DOOR_INFEASIBLE",
                    target=room.id,
                    severity="CRITICAL",
                    message=f"Room '{room.name}' ({room.id}) has no feasible door connection."
                ))

        # 3. Final Invariants Circulation Validation
        try:
            final_circ = validate_final_circulation_invariants(candidate)
            if not final_circ.get("circulation_valid", True):
                for viol in final_circ.get("hard_violations", []):
                    v_type = viol.get("type", "")
                    if v_type == "unreachable_room":
                        issues.append(AgentIssue(
                            issue_type="DISCONNECTED_ROOM",
                            target=viol.get("room"),
                            severity="CRITICAL",
                            message=f"Room '{viol.get('room')}' cannot be reached from Hall or exterior."
                        ))
                    elif "passage" in v_type:
                        issues.append(AgentIssue(
                            issue_type="PRIVATE_ROOM_AS_PASSAGE",
                            target=viol.get("passage_room"),
                            severity="CRITICAL",
                            message=f"Private room '{viol.get('passage_room')}' is used as mandatory passage for {viol.get('dependent_rooms')}."
                        ))
                    else:
                        issues.append(AgentIssue(
                            issue_type="CIRCULATION_VIOLATION",
                            severity="CRITICAL",
                            message=f"Circulation violation: {viol}"
                        ))
        except Exception as e:
            issues.append(AgentIssue(
                issue_type="CIRCULATION_CHECK_ERROR",
                severity="CRITICAL",
                message=f"Final circulation invariants check error: {str(e)}"
            ))

        # 4. Circulation Constraints Check
        try:
            circ_res = validate_circulation_constraints(candidate)
            if not circ_res.get("valid", True):
                for rej in circ_res.get("rejections", []):
                    if "_unreachable" in rej:
                        room_id = rej.replace("_unreachable", "")
                        if not any(i.issue_type == "DISCONNECTED_ROOM" and i.target == room_id for i in issues):
                            issues.append(AgentIssue(
                                issue_type="DISCONNECTED_ROOM",
                                target=room_id,
                                severity="CRITICAL",
                                message=f"Room '{room_id}' is unreachable."
                            ))
                    elif "passage_rejections" in rej:
                        if not any(i.issue_type == "PRIVATE_ROOM_AS_PASSAGE" for i in issues):
                            issues.append(AgentIssue(
                                issue_type="PRIVATE_ROOM_AS_PASSAGE",
                                severity="CRITICAL",
                                message=f"Circulation constraint rejected due to invalid passage: {rej}"
                            ))
                    elif "access_rejections" in rej:
                        issues.append(AgentIssue(
                            issue_type="DIRECT_ACCESS_VIOLATION",
                            severity="WARNING",
                            message=f"Direct Hall access requirement violated: {rej}"
                        ))
        except Exception as e:
            issues.append(AgentIssue(
                issue_type="CIRCULATION_CONSTRAINTS_ERROR",
                severity="WARNING",
                message=f"Circulation constraints check error: {str(e)}"
            ))

        # 5. Architectural Quality Evaluation
        arch_metrics = {}
        try:
            arch_eval = evaluate_architecture(candidate)
            arch_metrics["architectural_score"] = arch_eval.get("architectural_score", 0)
            diag = arch_eval.get("diagnostics", {})
            arch_metrics["circulation_score"] = diag.get("circulation_score", 0)
            arch_metrics["privacy_score"] = diag.get("privacy_score", 0)
            arch_metrics["direct_access_score"] = diag.get("direct_access_score", 0)
            arch_metrics["hall_direct_access_count"] = diag.get("hall_direct_access_count", 0)
            arch_metrics["indirect_access_count"] = diag.get("indirect_access_count", 0)
            arch_metrics["room_realism_rejections"] = diag.get("room_realism_rejections", 0)
            
            if diag.get("room_realism_rejections", 0) > 0:
                issues.append(AgentIssue(
                    issue_type="ROOM_REALISM_VIOLATION",
                    severity="WARNING",
                    message=f"{diag.get('room_realism_rejections')} room realism rejections detected in layout dimensions."
                ))
        except Exception as e:
            arch_metrics["error"] = str(e)

        # Determine overall status and recommended action
        critical_issues = [i for i in issues if i.severity == "CRITICAL"]
        warning_issues = [i for i in issues if i.severity == "WARNING"]
        
        if critical_issues:
            status = "FAIL"
            # Explicit mapping to recommended action
            if any(i.issue_type == "DISCONNECTED_ROOM" for i in critical_issues):
                recommended_action = "REGENERATE_LAYOUT"
            elif any(i.issue_type == "PRIVATE_ROOM_AS_PASSAGE" for i in critical_issues):
                recommended_action = "REGENERATE_LAYOUT"
            elif any(i.issue_type == "DOOR_INFEASIBLE" for i in critical_issues):
                recommended_action = "REGENERATE_LAYOUT"
            else:
                recommended_action = "REGENERATE_LAYOUT"
        elif warning_issues:
            status = "WARNING"
            recommended_action = "OPTIMIZE_LAYOUT"
        else:
            status = "SUCCESS"
            recommended_action = "NO_ACTION"

        duration = (time.time() - t0) * 1000
        res = AgentResult(
            agent_name=self.name,
            status=status,
            issues=issues,
            recommended_action=recommended_action,
            metrics=arch_metrics,
            actions=actions,
            duration_ms=round(duration, 2)
        )
        
        state.architecture_result = res
        # Append issues to state's active issue list
        for iss in issues:
            if not any(existing.issue_type == iss.issue_type and existing.target == iss.target for existing in state.active_issues):
                state.active_issues.append(iss)
                
        return res
