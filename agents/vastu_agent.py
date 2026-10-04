import time
from typing import Dict, Any, List
from agents.base import BaseAgent, AgentResult, AgentIssue, AgentAction
from agents.state import FloorPlanAgentState
from vastu.validator import analyze_vastu

class VastuAgent(BaseAgent):
    """
    VastuAgent:
    Analyzes directional placement, calculates Vastu scores, identifies preferred and
    avoidance zones, and provides recommendations for optimization.
    
    NON-NEGOTIABLE ARCHITECTURAL PRINCIPLE:
    Vastu is strictly a PREFERENCE/SCORING layer and NEVER a geometry authority.
    It does not override plot boundaries, overlap rules, connectivity, circulation, or realism.
    Priority hierarchy:
      1. Geometry validity
      2. Connectivity / circulation validity
      3. Architectural validity
      4. Vastu preference
      5. Space efficiency / compactness optimization
    """
    name: str = "VastuAgent"

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
                    message="VastuAgent requires a selected layout candidate."
                )],
                recommended_action="REGENERATE_LAYOUT",
                duration_ms=0.0
            )
            state.vastu_result = res
            return res

        # If Vastu analysis is disabled in user preferences, return benign SUCCESS
        if not state.enable_vastu:
            res = AgentResult(
                agent_name=self.name,
                status="SUCCESS",
                issues=[],
                recommended_action="NO_ACTION",
                metrics={"vastu_enabled": False, "score": 100.0},
                duration_ms=0.0
            )
            state.vastu_result = res
            return res

        try:
            # Deterministic Vastu analysis using existing authoritative engine
            vastu_report = analyze_vastu(state.selected_candidate)
            
            score = vastu_report.get("overall_score", vastu_report.get("score", 0.0))
            breakdown = vastu_report.get("breakdown", {})
            room_results = vastu_report.get("results", [])
            
            # Inspect room placements
            avoid_count = 0
            penalty_count = 0
            for item in room_results:
                room_id = item.get("room", "")
                room_name = item.get("name", room_id)
                status = item.get("status", "")
                zone = item.get("zone", "")
                reason = item.get("reason", "")
                
                if status == "violation":
                    avoid_count += 1
                    # In Vastu preference layer, avoid zone is recorded as WARNING (never overrides geometry)
                    issues.append(AgentIssue(
                        issue_type="VASTU_AVOID_ZONE",
                        target=room_id,
                        severity="WARNING",
                        message=f"{room_name.capitalize()} is located in avoidance zone {zone}: {reason}"
                    ))
                elif status == "penalty":
                    penalty_count += 1
                    issues.append(AgentIssue(
                        issue_type="VASTU_NON_PREFERRED_ZONE",
                        target=room_id,
                        severity="INFO",
                        message=f"{room_name.capitalize()} is in acceptable/neutral zone {zone} with minor penalty: {reason}"
                    ))

            if score < 70.0:
                issues.append(AgentIssue(
                    issue_type="LOW_VASTU_SCORE",
                    severity="WARNING",
                    message=f"Overall Vastu score {score:.1f}/100 is below the desired target (70.0)."
                ))

            # Recommended action is issue-driven:
            # If score is low or avoid zones exist, suggest VASTU_OPTIMIZE (if optimization enabled)
            if (score < 75.0 or avoid_count > 0) and state.enable_optimizer:
                recommended_action = "VASTU_OPTIMIZE"
            else:
                recommended_action = "NO_ACTION"

            # Vastu is a preference layer: its status is WARNING if score is low, but NEVER geometric FAIL
            status = "WARNING" if (score < 60.0 or avoid_count > 0) else "SUCCESS"
            
            duration = (time.time() - t0) * 1000
            res = AgentResult(
                agent_name=self.name,
                status=status,
                issues=issues,
                recommended_action=recommended_action,
                metrics={
                    "score": round(score, 1),
                    "avoid_zone_count": avoid_count,
                    "penalty_count": penalty_count,
                    "breakdown": breakdown,
                    "raw_report": vastu_report
                },
                actions=actions,
                duration_ms=round(duration, 2)
            )
            state.vastu_result = res
            
            # Record issues to active issues
            for iss in issues:
                if not any(e.issue_type == iss.issue_type and e.target == iss.target for e in state.active_issues):
                    state.active_issues.append(iss)
                    
            return res

        except Exception as e:
            duration = (time.time() - t0) * 1000
            issues.append(AgentIssue(
                issue_type="VASTU_ANALYSIS_FAILED",
                severity="WARNING",
                message=f"Vastu analysis threw error: {str(e)}"
            ))
            res = AgentResult(
                agent_name=self.name,
                status="WARNING",
                issues=issues,
                recommended_action="NO_ACTION",
                metrics={"error": str(e)},
                duration_ms=round(duration, 2)
            )
            state.vastu_result = res
            return res
