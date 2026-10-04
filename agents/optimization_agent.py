import time
from typing import Dict, Any, List, Optional, Tuple
from agents.base import BaseAgent, AgentResult, AgentIssue, AgentAction
from agents.state import FloorPlanAgentState
from layout.validator import validate_layout
from layout.architecture import validate_final_circulation_invariants
from layout.space_utilization import evaluate_space_utilization
from layout.global_packer import optimize_global_footprint
from layout.vastu_optimizer import optimize_layout

class OptimizationAgent(BaseAgent):
    """
    OptimizationAgent:
    Issue-driven decision and coordination layer around existing deterministic optimizers:
      - layout.vastu_optimizer.optimize_layout
      - layout.global_packer.optimize_global_footprint
      - layout.space_utilization.evaluate_space_utilization
      
    NON-NEGOTIABLE ARCHITECTURAL PRINCIPLES:
    1. Does NOT blindly execute every optimizer on every iteration.
    2. Does NOT duplicate optimization algorithms.
    3. Analyzes state -> Identifies dominant weakness -> Selects deterministic strategy -> Executes existing engine.
    4. If geometry or circulation is invalid, REFUSES to optimize space or Vastu; recommends RETRY_LAYOUT.
    5. If an optimization move causes geometry or circulation invalidity, REJECTS THE MOVE.
    """
    name: str = "OptimizationAgent"

    def diagnose_weakness(self, state: FloorPlanAgentState) -> Tuple[str, str, Optional[AgentIssue]]:
        """
        Diagnoses the dominant weakness of the current state.
        Returns: (weakness_type, recommended_action, optional_issue)
        """
        # 1. Critical Geometry check
        geom_issues = [i for i in state.active_issues if i.issue_type in [
            "GEOMETRY_INVALID", "ROOM_OVERLAP", "OUTSIDE_PLOT_BOUNDARY", "INVALID_DIMENSIONS", "ENTRANCE_INVALID"
        ] and i.severity == "CRITICAL"]
        if geom_issues:
            return "INVALID_GEOMETRY", "RETRY_LAYOUT", geom_issues[0]

        # 2. Critical Circulation check
        circ_issues = [i for i in state.active_issues if i.issue_type in [
            "DISCONNECTED_ROOM", "PRIVATE_ROOM_AS_PASSAGE", "DOOR_INFEASIBLE"
        ] and i.severity == "CRITICAL"]
        if circ_issues:
            return "INVALID_CIRCULATION", "RETRY_LAYOUT", circ_issues[0]

        # 3. Space utilization check
        if state.selected_candidate is not None:
            try:
                space = evaluate_space_utilization(state.selected_candidate)
                unused_area = space.get("unused_interior_area", 0.0)
                largest_gap = space.get("largest_unused_region", 0.0)
                coverage = space.get("envelope_coverage_ratio", 100.0)
                compactness = space.get("compactness_score", 100.0)
                utilization = space.get("space_utilization_score", 100.0)

                if unused_area > 15.0 or largest_gap > 20.0:
                    iss = AgentIssue(
                        issue_type="LARGE_UNUSED_SPACE",
                        severity="WARNING",
                        message=f"Large unused internal void detected: {largest_gap:.1f} sq.ft (total unused: {unused_area:.1f} sq.ft)."
                    )
                    return "LARGE_UNUSED_SPACE", "REDUCE_UNUSED_SPACE", iss

                if compactness < 65.0 or coverage < 70.0:
                    iss = AgentIssue(
                        issue_type="LOW_COMPACTNESS",
                        severity="WARNING",
                        message=f"Building footprint has low compactness ({compactness:.1f}/100) or low coverage ({coverage:.1f}%)."
                    )
                    return "LOW_COMPACTNESS", "REPACK_LAYOUT", iss

                if utilization < 65.0:
                    iss = AgentIssue(
                        issue_type="LOW_SPACE_UTILIZATION",
                        severity="WARNING",
                        message=f"Space utilization ratio ({utilization:.1f}/100) is below target."
                    )
                    return "LOW_SPACE_UTILIZATION", "EXPAND_ROOMS", iss
            except Exception as e:
                pass

        # 4. Vastu preference check (only if enabled and geometry/circulation are sound)
        if state.enable_vastu:
            vastu_avoid = [i for i in state.active_issues if i.issue_type == "VASTU_AVOID_ZONE"]
            if vastu_avoid:
                return "VASTU_AVOID_ZONE", "VASTU_OPTIMIZE", vastu_avoid[0]
                
            low_vastu = [i for i in state.active_issues if i.issue_type == "LOW_VASTU_SCORE"]
            if low_vastu:
                return "LOW_VASTU_SCORE", "VASTU_OPTIMIZE", low_vastu[0]

        return "NONE", "NO_ACTION", None

    def run(self, state: FloorPlanAgentState) -> AgentResult:
        t0 = time.time()
        issues: List[AgentIssue] = []
        actions: List[AgentAction] = []
        metrics: Dict[str, Any] = {}

        if state.selected_candidate is None:
            res = AgentResult(
                agent_name=self.name,
                status="FAIL",
                issues=[AgentIssue(
                    issue_type="NO_LAYOUT_CANDIDATE",
                    severity="CRITICAL",
                    message="OptimizationAgent requires a candidate layout to optimize."
                )],
                recommended_action="REGENERATE_LAYOUT",
                duration_ms=0.0
            )
            state.optimization_result = res
            return res

        # 1. Diagnose dominant weakness
        weakness, strategy, issue = self.diagnose_weakness(state)
        metrics["diagnosed_weakness"] = weakness
        metrics["selected_strategy"] = strategy

        if issue:
            issues.append(issue)

        # 2. If geometry or circulation is invalid, REFUSE to optimize; trigger retry
        if strategy in ["RETRY_LAYOUT", "REGENERATE_LAYOUT"]:
            res = AgentResult(
                agent_name=self.name,
                status="FAIL",
                issues=issues,
                recommended_action="REGENERATE_LAYOUT",
                metrics=metrics,
                duration_ms=round((time.time() - t0) * 1000, 2)
            )
            state.optimization_result = res
            return res

        # 3. If no weakness detected, NO_ACTION
        if strategy == "NO_ACTION" or not state.enable_optimizer:
            res = AgentResult(
                agent_name=self.name,
                status="SUCCESS",
                issues=issues,
                recommended_action="NO_ACTION",
                metrics=metrics,
                duration_ms=round((time.time() - t0) * 1000, 2)
            )
            state.optimization_result = res
            return res

        reqs = state.requirements
        plot_w = state.selected_candidate.plot_width
        plot_d = state.selected_candidate.plot_depth
        facing = reqs.plot.facing if (reqs and reqs.plot) else "north"
        prev_layout = state.selected_candidate

        # 4. Deterministic Strategy Execution
        try:
            if strategy in ["REDUCE_UNUSED_SPACE", "REPACK_LAYOUT", "EXPAND_ROOMS"]:
                # Execute existing global footprint packer
                actions.append(AgentAction(
                    action_type=strategy,
                    target="footprint",
                    reason=f"Optimizing footprint to resolve {weakness} using layout.global_packer."
                ))
                best_fp, best_space = optimize_global_footprint(
                    state.selected_candidate, reqs, plot_w, plot_d, facing
                )
                
                # Verify that geometry and circulation invariants were preserved
                val = validate_layout(best_fp)
                circ = validate_final_circulation_invariants(best_fp)
                
                if val.get("valid", False) and circ.get("circulation_valid", False):
                    state.selected_candidate = best_fp
                    metrics["optimization_applied"] = True
                    metrics["space_utilization_after"] = best_space
                else:
                    # REJECT MOVE if it broke geometry or circulation
                    state.selected_candidate = prev_layout
                    metrics["optimization_applied"] = False
                    metrics["rejection_reason"] = "Move produced invalid geometry or circulation; reverted."
                    issues.append(AgentIssue(
                        issue_type="OPTIMIZATION_REJECTED",
                        severity="WARNING",
                        message="Footprint packing was rejected because it degraded geometric or circulation validity."
                    ))

            elif strategy == "VASTU_OPTIMIZE":
                # Execute existing Vastu layout optimizer
                actions.append(AgentAction(
                    action_type="VASTU_OPTIMIZE",
                    target="vastu",
                    reason=f"Executing Vastu optimization to resolve {weakness} using layout.vastu_optimizer."
                ))
                baseline_vastu = state.vastu_result.metrics.get("raw_report", {}) if state.vastu_result else {}
                best_layout, best_vastu, opt_meta = optimize_layout(reqs, state.selected_candidate, baseline_vastu)
                
                # Verify geometric and circulation invariants
                val = validate_layout(best_layout)
                circ = validate_final_circulation_invariants(best_layout)
                
                if val.get("valid", False) and circ.get("circulation_valid", False):
                    state.selected_candidate = best_layout
                    metrics["optimization_applied"] = True
                    metrics["vastu_score_after"] = best_vastu.get("score", 0)
                    metrics["opt_meta"] = opt_meta
                else:
                    # REJECT MOVE: Vastu MUST NOT override geometry or circulation
                    state.selected_candidate = prev_layout
                    metrics["optimization_applied"] = False
                    metrics["rejection_reason"] = "Vastu optimizer candidate violated geometry or circulation; move rejected."
                    issues.append(AgentIssue(
                        issue_type="VASTU_OPTIMIZATION_REJECTED",
                        severity="WARNING",
                        message="Vastu candidate was rejected because geometric and circulation validity take precedence."
                    ))

            status = "SUCCESS" if metrics.get("optimization_applied", False) else "WARNING"
            recommended_action = "VALIDATE"
            
        except Exception as e:
            issues.append(AgentIssue(
                issue_type="OPTIMIZATION_ERROR",
                severity="WARNING",
                message=f"Optimizer threw error: {str(e)}"
            ))
            status = "WARNING"
            recommended_action = "VALIDATE"
            metrics["error"] = str(e)

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
        state.optimization_result = res
        return res
