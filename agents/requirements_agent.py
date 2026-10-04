import time
from agents.base import BaseAgent, AgentResult, AgentIssue
from agents.state import FloorPlanAgentState
from llm.parser import parse_requirements

class RequirementsAgent(BaseAgent):
    name: str = "RequirementsAgent"

    def run(self, state: FloorPlanAgentState) -> AgentResult:
        t0 = time.time()
        issues = []
        
        # If requirements are already parsed and valid, avoid duplicate Gemini calls
        if state.requirements is not None:
            return AgentResult(
                agent_name=self.name,
                status="SUCCESS",
                issues=[],
                recommended_action="GENERATE_LAYOUT",
                metrics={"cached": True},
                duration_ms=0.0
            )
            
        try:
            # ONE Gemini call per user request
            reqs = parse_requirements(state.user_prompt, test_case_name=state.request_id)
            state.requirements = reqs
            
            # Basic consistency checks
            if reqs.plot.width <= 0 or reqs.plot.depth <= 0:
                issues.append(AgentIssue(
                    issue_type="INVALID_PLOT_DIMENSIONS",
                    severity="CRITICAL",
                    message=f"Invalid plot dimensions: {reqs.plot.width}x{reqs.plot.depth}"
                ))
            if not reqs.rooms or sum(reqs.rooms.values()) == 0:
                issues.append(AgentIssue(
                    issue_type="NO_ROOMS_SPECIFIED",
                    severity="CRITICAL",
                    message="No rooms were parsed from the user prompt."
                ))
                
            status = "FAIL" if any(i.severity == "CRITICAL" for i in issues) else "SUCCESS"
            duration = (time.time() - t0) * 1000
            
            res = AgentResult(
                agent_name=self.name,
                status=status,
                issues=issues,
                recommended_action="GENERATE_LAYOUT" if status == "SUCCESS" else "RETRY_PARSING",
                metrics={
                    "plot_width": reqs.plot.width,
                    "plot_depth": reqs.plot.depth,
                    "facing": reqs.plot.facing,
                    "room_count": sum(reqs.rooms.values()),
                    "parking": reqs.parking
                },
                duration_ms=round(duration, 2)
            )
            state.requirements_result = res
            return res
            
        except Exception as e:
            duration = (time.time() - t0) * 1000
            issues.append(AgentIssue(
                issue_type="REQUIREMENTS_PARSING_FAILED",
                severity="CRITICAL",
                message=str(e)
            ))
            res = AgentResult(
                agent_name=self.name,
                status="FAIL",
                issues=issues,
                recommended_action="ABORT",
                metrics={"error": str(e)},
                duration_ms=round(duration, 2)
            )
            state.requirements_result = res
            state.error_message = str(e)
            return res
