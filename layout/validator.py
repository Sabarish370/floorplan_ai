from shapely.geometry import box
from shapely.ops import unary_union
from models.floorplan import FloorPlan
from typing import Dict, Any
from layout.orientation import normalize_orientation, get_boundary_coordinate, is_point_on_boundary

def validate_layout(plan: FloorPlan) -> Dict[str, Any]:
    plot_polygon = box(0, 0, plan.plot_width, plan.plot_depth)
    plot_area = plan.plot_width * plan.plot_depth
    
    errors = []
    warnings = []
    
    room_polygons = []
    parking_polygons = []
    
    for room in plan.rooms:
        w, h = room.width, room.depth
        if w <= 0 or h <= 0:
            errors.append(f"Room '{room.name}' has invalid dimensions: {w}x{h}")
            continue
            
        room_poly = box(room.x, room.y, room.x + w, room.y + h)
        
        if not plot_polygon.contains(room_poly):
            errors.append(f"Room '{room.name}' is outside the plot boundary.")
            
        # Check overlaps
        all_polys = room_polygons + parking_polygons
        for j, other_poly in enumerate(all_polys):
            if room_poly.overlaps(other_poly):
                intersection = room_poly.intersection(other_poly)
                if intersection.area > 0.01:
                    errors.append(f"Room '{room.name}' overlaps with another room.")
                    
        if room.type == 'parking':
            parking_polygons.append(room_poly)
        else:
            room_polygons.append(room_poly)
            
    # Area Accounting via Unions
    room_union = unary_union(room_polygons) if room_polygons else box(0,0,0,0)
    parking_union = unary_union(parking_polygons) if parking_polygons else box(0,0,0,0)
    building_union = unary_union(room_polygons) if room_polygons else box(0,0,0,0)
    occupied_union = unary_union(room_polygons + parking_polygons) if (room_polygons or parking_polygons) else box(0,0,0,0)
    
    room_area = room_union.area
    parking_area = parking_union.area
    building_area = building_union.area
    occupied_area = occupied_union.area
    external_open_area = plot_area - occupied_area
    unallocated_buildable_area = plot_area - occupied_area # Simplified
    
    # CONNECTIVITY & ENTRANCE FACING VALIDATION
    connections = []
    
    if not plan.entrance:
        errors.append("Main entrance is missing.")
    else:
        if plan.entrance.room != "hall_1" and not any(r.id == plan.entrance.room and r.type in ['hall', 'living'] for r in plan.rooms):
            errors.append("Main entrance must connect to hall or a valid public space.")
        else:
            connections.append(["exterior", plan.entrance.room])
            
        # Validate ENTRANCE_FACING
        requested_facing = normalize_orientation(plan.plot.facing) if hasattr(plan, 'plot') and plan.plot else plan.entrance.side
        if plan.entrance.side != requested_facing:
            errors.append(f"Entrance orientation mismatch: requested={requested_facing}, actual={plan.entrance.side}")
            
        # Verify physical location
        if not is_point_on_boundary(plan.entrance.x, plan.entrance.y, plan.entrance.side, plan.plot_width, plan.plot_depth):
            # Check the other dimension depending on axis
            axis, _, _, _ = get_boundary_coordinate(plan.entrance.side, plan.plot_width, plan.plot_depth)
            if axis == 'x':
                if not is_point_on_boundary(plan.entrance.x, plan.entrance.y + plan.entrance.width, plan.entrance.side, plan.plot_width, plan.plot_depth):
                    errors.append("Entrance is not on the requested plot boundary.")
            else:
                if not is_point_on_boundary(plan.entrance.x + plan.entrance.width, plan.entrance.y, plan.entrance.side, plan.plot_width, plan.plot_depth):
                    errors.append("Entrance is not on the requested plot boundary.")
            
    if plan.vehicle_gate:
        connections.append(["exterior", "vehicle_gate"])
        connections.append(["vehicle_gate", plan.vehicle_gate.room])
        # Verify physical location
        if not is_point_on_boundary(plan.vehicle_gate.x, plan.vehicle_gate.y, plan.vehicle_gate.side, plan.plot_width, plan.plot_depth):
            axis, _, _, _ = get_boundary_coordinate(plan.vehicle_gate.side, plan.plot_width, plan.plot_depth)
            if axis == 'x':
                if not is_point_on_boundary(plan.vehicle_gate.x, plan.vehicle_gate.y + plan.vehicle_gate.width, plan.vehicle_gate.side, plan.plot_width, plan.plot_depth):
                    errors.append("Vehicle gate is not on the requested plot boundary.")
            else:
                if not is_point_on_boundary(plan.vehicle_gate.x + plan.vehicle_gate.width, plan.vehicle_gate.y, plan.vehicle_gate.side, plan.plot_width, plan.plot_depth):
                    errors.append("Vehicle gate is not on the requested plot boundary.")
    else:
        parking_r = next((r for r in plan.rooms if r.type == 'parking'), None)
        if parking_r:
            errors.append("Parking requires a vehicle gate.")
            
    # Build a simple graph
    graph = {r.id: [] for r in plan.rooms}
    for d in plan.doors:
        if d.from_room.startswith('parking') or d.to_room.startswith('parking'):
            errors.append(f"Parking must not connect internally to {d.to_room if d.from_room.startswith('parking') else d.from_room}.")
            
        if d.from_room in graph:
            graph[d.from_room].append(d.to_room)
        if d.to_room in graph:
            graph[d.to_room].append(d.from_room)
        connections.append([d.from_room, d.to_room])
            
    # Traversal from Hall or primary entrance room
    visited = set()
    start_room_id = plan.entrance.room if plan.entrance else None
    if not start_room_id:
        hall = next((r for r in plan.rooms if r.type == 'hall'), None)
        start_room_id = hall.id if hall else None
        
    if start_room_id and start_room_id in graph:
        queue = [start_room_id]
        while queue:
            curr = queue.pop(0)
            if curr not in visited:
                visited.add(curr)
                for neighbor in graph.get(curr, []):
                    if neighbor not in visited:
                        queue.append(neighbor)
                        
    # Check for isolated rooms (exclude parking)
    for room in plan.rooms:
        if room.type != 'parking' and room.id not in visited:
            errors.append(f"{room.name.capitalize()} is not accessible.")
            
    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "connections": connections,
        "orientation_valid": len([e for e in errors if "orientation" in e.lower() or "boundary" in e.lower()]) == 0,
        "metrics": {
            "plot_area": plot_area,
            "room_area": room_area,
            "parking_area": parking_area,
            "building_area": building_area,
            "occupied_area": occupied_area,
            "external_open_area": external_open_area,
            "unallocated_buildable_area": unallocated_buildable_area,
            "built_area": building_area,
            "utilization_percentage": (occupied_area / plot_area * 100) if plot_area > 0 else 0
        }
    }
