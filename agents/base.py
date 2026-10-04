from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

class AgentIssue(BaseModel):
    issue_type: str        # e.g., DISCONNECTED_ROOM, GEOMETRY_INVALID, ROOM_OVERLAP, PRIVATE_ROOM_AS_PASSAGE, LARGE_UNUSED_SPACE
    target: Optional[str] = None  # e.g., "bedroom_2", "kitchen_1"
    severity: str = "CRITICAL"    # "CRITICAL", "WARNING", "INFO"
    message: str = ""

class AgentAction(BaseModel):
    action_type: str       # e.g., REGENERATE_LAYOUT, REDUCE_UNUSED_SPACE, EXPAND_ROOMS, REPACK_LAYOUT, VASTU_OPTIMIZE, NO_ACTION
    target: Optional[str] = None
    reason: Optional[str] = None
    parameters: Dict[str, Any] = Field(default_factory=dict)

class AgentResult(BaseModel):
    agent_name: str
    status: str            # "SUCCESS", "WARNING", "FAIL"
    issues: List[AgentIssue] = Field(default_factory=list)
    recommended_action: Optional[str] = None
    metrics: Dict[str, Any] = Field(default_factory=dict)
    actions: List[AgentAction] = Field(default_factory=list)
    duration_ms: float = 0.0

class BaseAgent(ABC):
    name: str

    @abstractmethod
    def run(self, state: Any) -> AgentResult:
        """
        Executes the agent's deterministic responsibility on the shared state.
        Must NOT mutate unrelated state.
        Returns a typed AgentResult.
        """
        pass
