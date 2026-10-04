from pydantic import BaseModel, Field
from typing import Literal, Dict, Optional, Any

class Plot(BaseModel):
    width: float = Field(..., description="Width of the plot")
    depth: float = Field(..., description="Depth of the plot")
    unit: str = Field(..., description="Unit of measurement, e.g., 'ft' or 'm'")
    facing: Literal["north", "south", "east", "west", "unknown"] = Field("unknown", description="Facing direction of the house")
    area: Optional[float] = Field(None, description="Area of the plot if stated")

class FloorPlanRequirements(BaseModel):
    plot: Plot = Field(..., description="Plot dimensions and orientation")
    rooms: Dict[str, int] = Field(default_factory=dict, description="Dictionary mapping room names (e.g., 'bedroom', 'hall') to the required count")
    parking: bool = Field(False, description="Whether parking is required")
    vastu_enabled: bool = Field(False, description="Whether Vastu principles should be applied (not implemented yet)")
    request_id: str = Field("unknown", description="Request ID for logging")
    test_case_name: str = Field("UNKNOWN TEST CASE", description="Test case name for logging")
