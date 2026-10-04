import time
from agents.base import BaseAgent, AgentResult, AgentIssue
from agents.state import FloorPlanAgentState
from layout.generator import generate_layout, generate_layout_beam_search

class LayoutAgent(BaseAgent):
    name: str = "LayoutAgent"

    def run(self, state: FloorPlanAgentState) -> AgentResult:
        t0 = time.time()
        issues = []
        
        if not state.requirements:
            return AgentResult(
                agent_name=self.name,
                status="FAIL",
                issues=[AgentIssue(
                    issue_type="MISSING_REQUIREMENTS",
                    severity="CRITICAL",
                    message="Requirements must be parsed before generating layout."
                )],
                recommended_action="PARSE_REQUIREMENTS",
                duration_ms=0.0
            )
            
        reqs = state.requirements
        strategy = state.preferred_strategy or ("vastu_first" if state.enable_vastu else "baseline")
        
        try:
            candidates = []
            metrics = {}
            
            # Use deterministic beam search or baseline generator
            if strategy == 'baseline':
                base_cand = generate_layout(reqs, seed=42 + state.iteration, strategy='baseline')
                candidates = [base_cand]
                metrics["search_type"] = "baseline"
                metrics["candidate_count"] = 1
            else:
                beam_cands, s_metrics = generate_layout_beam_search(
                    reqs,
                    strategy=strategy,
                    beam_width=15,
                    max_candidates_per_room=6
                )
                candidates = beam_cands
                metrics = s_metrics
                metrics["search_type"] = "beam_search"
                metrics["candidate_count"] = len(beam_cands)
                
                # If chosen beam strategy dead-ended, try alternative beam strategies
                if not candidates:
                    for alt_strat in ['kitchen_first', 'bedroom_first', 'balanced']:
                        if alt_strat == strategy:
                            continue
                        alt_cands, alt_metrics = generate_layout_beam_search(
                            reqs,
                            strategy=alt_strat,
                            beam_width=15,
                            max_candidates_per_room=6
                        )
                        if alt_cands:
                            candidates = alt_cands
                            metrics = alt_metrics
                            metrics["search_type"] = f"beam_search_{alt_strat}"
                            metrics["candidate_count"] = len(alt_cands)
                            break
                            
            if not candidates:
                # Fallback to deterministic baseline generator if all beam search strategies produced no candidate
                fallback = generate_layout(reqs, seed=42 + state.iteration, strategy='baseline')
                candidates = [fallback]
                issues.append(AgentIssue(
                    issue_type="BEAM_SEARCH_FALLBACK",
                    severity="WARNING",
                    message="Beam search yielded no complete candidate; fell back to baseline generator."
                ))
                
            # Prioritize candidate that already satisfies layout and circulation invariants
            selected = candidates[0]
            for c in candidates:
                from layout.validator import validate_layout
                from layout.architecture import validate_final_circulation_invariants
                if validate_layout(c).get("valid", False) and validate_final_circulation_invariants(c).get("circulation_valid", False):
                    selected = c
                    break
            state.selected_candidate = selected
            state.top_candidates = candidates[:3]  # Keep lean, avoid storing hundreds
            
            duration = (time.time() - t0) * 1000
            res = AgentResult(
                agent_name=self.name,
                status="SUCCESS",
                issues=issues,
                recommended_action="VALIDATE_ARCHITECTURE",
                metrics=metrics,
                duration_ms=round(duration, 2)
            )
            state.layout_result = res
            return res
            
        except Exception as e:
            duration = (time.time() - t0) * 1000
            issues.append(AgentIssue(
                issue_type="LAYOUT_GENERATION_FAILED",
                severity="CRITICAL",
                message=str(e)
            ))
            res = AgentResult(
                agent_name=self.name,
                status="FAIL",
                issues=issues,
                recommended_action="RETRY_LAYOUT",
                metrics={"error": str(e)},
                duration_ms=round(duration, 2)
            )
            state.layout_result = res
            return res
