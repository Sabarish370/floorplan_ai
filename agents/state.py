from enum import Enum
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from models.requirements import FloorPlanRequirements
from models.floorplan import FloorPlan
from agents.base import AgentIssue, AgentAction, AgentResult

class OrchestrationStatus(str, Enum):
    INITIALIZING = "INITIALIZING"
    REQUIREMENTS_PARSED = "REQUIREMENTS_PARSED"
    VALID = "VALID"
    RETRYABLE_FAILURE = "RETRYABLE_FAILURE"
    INFEASIBLE_REQUEST = "INFEASIBLE_REQUEST"
    FAILED = "FAILED"

class FailureClassification(str, Enum):
    NONE = "NONE"
    RETRYABLE_FAILURE = "RETRYABLE_FAILURE"
    INFEASIBLE_REQUEST = "INFEASIBLE_REQUEST"

class AgentTraceStep(BaseModel):
    agent_name: str
    iteration: int
    status: str
    action_taken: Optional[str] = None
    duration_ms: float = 0.0
    message: str = ""

class FloorPlanAgentState(BaseModel):
    request_id: str
    user_prompt: str
    
    # Requirements (Structured, set by RequirementsAgent)
    requirements: Optional[FloorPlanRequirements] = None
    
    # Floor plan candidate models
    selected_candidate: Optional[FloorPlan] = None
    top_candidates: List[FloorPlan] = Field(default_factory=list)
    
    # Agent Results
    requirements_result: Optional[AgentResult] = None
    layout_result: Optional[AgentResult] = None
    architecture_result: Optional[AgentResult] = None
    vastu_result: Optional[AgentResult] = None
    optimization_result: Optional[AgentResult] = None
    validation_result: Optional[AgentResult] = None
    
    # Iteration & Lifecycle Control
    iteration: int = 0
    max_iterations: int = 3
    is_valid: bool = False
    status: str = "INITIALIZING"  # "INITIALIZING", "REQUIREMENTS_PARSED", "GENERATING", "OPTIMIZING", "VALIDATING", "SUCCESS", "FAILED", "INFEASIBLE_REQUEST"
    
    # Orchestration Outcome & Failure Classification
    orchestration_status: OrchestrationStatus = OrchestrationStatus.INITIALIZING
    failure_classification: FailureClassification = FailureClassification.NONE
    diagnosis_reason: Optional[str] = None
    affected_rooms: List[str] = Field(default_factory=list)
    structural_evidence: Dict[str, Any] = Field(default_factory=dict)
    retry_recommended: bool = True
    infeasibility_reasons: List[str] = Field(default_factory=list)
    recommended_relaxations: List[str] = Field(default_factory=list)
    attempted_iterations: int = 0

    # Settings
    enable_vastu: bool = True
    enable_optimizer: bool = True
    preferred_strategy: Optional[str] = None
    
    # Diagnosis & Action Tracking
    active_issues: List[AgentIssue] = Field(default_factory=list)
    action_history: List[AgentAction] = Field(default_factory=list)
    trace: List[AgentTraceStep] = Field(default_factory=list)
    error_message: Optional[str] = None

    def get_infeasibility_summary(self) -> Dict[str, Any]:
        return {
            "status": self.orchestration_status.value,
            "reason": self.diagnosis_reason or self.error_message or "No valid plan was found under current constraints.",
            "dominant_issue": self.structural_evidence.get("dominant_issue", "unknown"),
            "affected_rooms": self.affected_rooms,
            "structural_evidence": self.structural_evidence,
            "attempted_iterations": self.attempted_iterations,
            "recommended_relaxations": self.recommended_relaxations
        }
