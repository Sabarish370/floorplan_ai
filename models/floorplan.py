from pydantic import BaseModel
from typing import List, Optional

class Door(BaseModel):
    id: str
    type: str  # "internal", "external"
    from_room: str
    to_room: str
    wall_side: str
    x: float
    y: float
    width: float

class Entrance(BaseModel):
    id: str
    side: str
    room: str
    x: float
    y: float
    width: float

class VehicleGate(BaseModel):
    id: str
    side: str
    room: str
    x: float
    y: float
    width: float

class Room(BaseModel):
    id: str
    type: str
    name: str
    x: float
    y: float
    width: float
    depth: float
    area: float

class FloorPlan(BaseModel):
    plot_width: float
    plot_depth: float
    plot_area: float
    built_area: float
    utilization_percentage: float
    facing: str
    rooms: List[Room]
    doors: List[Door]
    entrance: Optional[Entrance] = None
    vehicle_gate: Optional[VehicleGate] = None
