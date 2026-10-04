from models.floorplan import Door
from geometry.geometry_utils import get_shared_edge

def generate_internal_doors(rooms: list) -> list:
    """
    Generates internal doors between rooms.
    Uses a Prim's algorithm approach to build a single spanning tree from the Hall,
    ensuring all rooms are reachable.
    """
    doors = []
    
    hall = next((r for r in rooms if r['type'] == 'hall'), None)
    if not hall:
        hall = rooms[0] if rooms else None
        
    if not hall:
        return doors

    door_id_counter = 1
    
    connected_rooms = {hall['id']}
    unconnected_rooms = {r['id']: r for r in rooms if r['id'] != hall['id'] and r['type'] != 'parking'}
    
    def can_be_parent(c_room_type, u_room_type):
        c_base = c_room_type.split('_')[0]
        u_base = u_room_type.split('_')[0]
        
        # Public rooms can parent anything
        if c_base in ['hall', 'dining', 'living', 'circulation', 'corridor', 'passage', 'foyer']:
            return True
            
        # Exception: Bedroom can parent an attached bathroom
        if c_base == 'bedroom' and u_base == 'bathroom':
            return True
            
        # Exception: Kitchen can parent a pooja room or another kitchen (wet/dry kitchen split)
        if c_base == 'kitchen' and u_base in ['pooja', 'kitchen']:
            return True
            
        return False

    while unconnected_rooms:
        best_edge = None
        best_priority = 999
        best_edge_len = -1.0
        best_room_to_connect = None
        best_connected_room = None
        
        for u_id, u_room in unconnected_rooms.items():
            for c_id in connected_rooms:
                c_room = next((r for r in rooms if r['id'] == c_id), None)
                if not c_room: continue
                
                edge = get_shared_edge(u_room, c_room)
                if edge:
                    edge_len_x = abs(edge['x2'] - edge['x1'])
                    edge_len_y = abs(edge['y2'] - edge['y1'])
                    if edge_len_x >= 3.0 or edge_len_y >= 3.0:
                        
                        if not can_be_parent(c_room['type'], u_room['type']):
                            continue
                            
                        # Prevent a single bedroom from parenting multiple bathrooms
                        if c_room['type'].startswith('bedroom') and u_room['type'].startswith('bathroom'):
                            count = sum(1 for d in doors if (d.from_room == c_room['id'] and d.to_room.startswith('bathroom')) or 
                                                           (d.to_room == c_room['id'] and d.from_room.startswith('bathroom')))
                            if count >= 1:
                                continue
                            
                        priority = 10 if c_room['type'].split('_')[0] not in ['hall', 'circulation'] else 0
                        edge_len = max(edge_len_x, edge_len_y)
                        
                        if priority < best_priority or (priority == best_priority and edge_len > best_edge_len):
                            best_priority = priority
                            best_edge_len = edge_len
                            best_edge = edge
                            best_room_to_connect = u_room
                            best_connected_room = c_room
                            
        if best_edge:
            door_width = 3.0
            edge_len_x = abs(best_edge['x2'] - best_edge['x1'])
            edge_len_y = abs(best_edge['y2'] - best_edge['y1'])
            
            if edge_len_x >= door_width:
                cx = (best_edge['x1'] + best_edge['x2']) / 2
                cy = best_edge['y1']
                doors.append(Door(
                    id=f"door_{door_id_counter}",
                    type="internal",
                    from_room=best_connected_room['id'],
                    to_room=best_room_to_connect['id'],
                    wall_side="horizontal",
                    x=cx - door_width/2,
                    y=cy,
                    width=door_width
                ))
            elif edge_len_y >= door_width:
                cx = best_edge['x1']
                cy = (best_edge['y1'] + best_edge['y2']) / 2
                doors.append(Door(
                    id=f"door_{door_id_counter}",
                    type="internal",
                    from_room=best_connected_room['id'],
                    to_room=best_room_to_connect['id'],
                    wall_side="vertical",
                    x=cx,
                    y=cy - door_width/2,
                    width=door_width
                ))
            door_id_counter += 1
            connected_rooms.add(best_room_to_connect['id'])
            del unconnected_rooms[best_room_to_connect['id']]
        else:
            # If no edge can be found (shouldn't happen with strict compactness), break to avoid infinite loop
            break
            
    return doors
