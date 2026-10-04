from models.floorplan import Entrance, VehicleGate
from layout.orientation import normalize_orientation, get_boundary_coordinate, is_room_on_boundary

def create_main_entrance(plot_width: float, plot_depth: float, facing: str, layout_rooms: list) -> Entrance:
    hall = next((r for r in layout_rooms if r['type'] == 'hall'), None)
    if not hall:
        hall = layout_rooms[0] if layout_rooms else None
        
    if not hall:
        return None
        
    w = 4.0
    facing = normalize_orientation(facing)
    axis, min_val, max_val, target_val = get_boundary_coordinate(facing, plot_width, plot_depth)
    
    # Place entrance precisely on the requested boundary.
    if axis == 'x':
        x = target_val
        y = max(hall['y'], min(hall['y'] + hall['depth'] / 2 - w/2, hall['y'] + hall['depth'] - w))
    else:
        y = target_val
        x = max(hall['x'], min(hall['x'] + hall['width'] / 2 - w/2, hall['x'] + hall['width'] - w))
        
    return Entrance(
        id="main_entrance",
        side=facing,
        room=hall['id'],
        x=x,
        y=y,
        width=w
    )

def create_vehicle_gate(plot_width: float, plot_depth: float, facing: str, layout_rooms: list) -> VehicleGate:
    parking = next((r for r in layout_rooms if r['type'] == 'parking'), None)
    if not parking:
        return None
        
    w = 10.0
    facing = normalize_orientation(facing)
    axis, min_val, max_val, target_val = get_boundary_coordinate(facing, plot_width, plot_depth)
    
    if axis == 'x':
        x = target_val
        y = max(parking['y'], min(parking['y'] + parking['depth'] / 2 - w/2, parking['y'] + parking['depth'] - w))
    else:
        y = target_val
        x = max(parking['x'], min(parking['x'] + parking['width'] / 2 - w/2, parking['x'] + parking['width'] - w))
        
    return VehicleGate(
        id="vehicle_gate_1",
        side=facing,
        room=parking['id'],
        x=x,
        y=y,
        width=w
    )
