def normalize_orientation(facing: str) -> str:
    facing = facing.lower().strip()
    if facing not in ['north', 'south', 'east', 'west']:
        return 'east'
    return facing

def get_facing_boundary(facing: str) -> str:
    """Returns the boundary corresponding to the facing direction."""
    return normalize_orientation(facing)

def get_opposite_boundary(facing: str) -> str:
    facing = normalize_orientation(facing)
    opposites = {
        'north': 'south',
        'south': 'north',
        'east': 'west',
        'west': 'east'
    }
    return opposites[facing]

def get_boundary_coordinate(facing: str, plot_width: float, plot_depth: float):
    """
    Returns (axis, min_val, max_val, target_val) for a given boundary.
    axis: 'x' or 'y'
    min_val: minimum coordinate for this axis
    max_val: maximum coordinate for this axis
    target_val: the specific coordinate value for this boundary
    """
    facing = normalize_orientation(facing)
    if facing == 'north':
        return ('y', 0.0, plot_width, 0.0)
    elif facing == 'south':
        return ('y', 0.0, plot_width, plot_depth)
    elif facing == 'west':
        return ('x', 0.0, plot_depth, 0.0)
    elif facing == 'east':
        return ('x', 0.0, plot_depth, plot_width)

def get_interior_direction_from_facing(facing: str) -> str:
    """If facing a boundary from the outside, which direction is the interior?"""
    return get_opposite_boundary(facing)

def is_point_on_boundary(x: float, y: float, boundary: str, plot_width: float, plot_depth: float, tol=0.1) -> bool:
    boundary = normalize_orientation(boundary)
    if boundary == 'north':
        return abs(y - 0.0) <= tol
    elif boundary == 'south':
        return abs(y - plot_depth) <= tol
    elif boundary == 'west':
        return abs(x - 0.0) <= tol
    elif boundary == 'east':
        return abs(x - plot_width) <= tol
    return False

def is_room_on_boundary(room: dict, boundary: str, plot_width: float, plot_depth: float, tol=0.1) -> bool:
    """Checks if a room touches the given boundary."""
    boundary = normalize_orientation(boundary)
    if boundary == 'north':
        return abs(room['y']) <= tol
    elif boundary == 'south':
        return abs((room['y'] + room['depth']) - plot_depth) <= tol
    elif boundary == 'west':
        return abs(room['x']) <= tol
    elif boundary == 'east':
        return abs((room['x'] + room['width']) - plot_width) <= tol
    return False
