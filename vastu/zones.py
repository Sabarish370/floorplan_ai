from typing import Dict, Tuple

ZONE_THRESHOLDS = {
    "low": 0.333,
    "high": 0.667
}

def get_zone(x: float, y: float, w: float, d: float, plot_width: float, plot_depth: float, facing: str = 'east') -> str:
    """
    Calculate the Vastu directional zone for a given room geometry.
    Returns one of: NW, N, NE, W, CENTER, E, SW, S, SE.
    """
    if plot_width <= 0 or plot_depth <= 0:
        return "UNKNOWN"
        
    cx = x + w / 2
    cy = y + d / 2
    
    # Normalize
    x_ratio = cx / plot_width
    y_ratio = cy / plot_depth
    
    # In the current geographic system:
    # x=0 is West, x=plot_width is East
    # y=0 is North, y=plot_depth is South
    # (East is right, West is left, North is top, South is bottom)
    
    if x_ratio < ZONE_THRESHOLDS["low"]:
        x_zone = 'W'
    elif x_ratio > ZONE_THRESHOLDS["high"]:
        x_zone = 'E'
    else:
        x_zone = 'C'
        
    if y_ratio < ZONE_THRESHOLDS["low"]:
        y_zone = 'N'
    elif y_ratio > ZONE_THRESHOLDS["high"]:
        y_zone = 'S'
    else:
        y_zone = 'C'
        
    if x_zone == 'C' and y_zone == 'C': return 'CENTER'
    if x_zone == 'W' and y_zone == 'N': return 'NW'
    if x_zone == 'E' and y_zone == 'N': return 'NE'
    if x_zone == 'W' and y_zone == 'S': return 'SW'
    if x_zone == 'E' and y_zone == 'S': return 'SE'
    if x_zone == 'C' and y_zone == 'N': return 'N'
    if x_zone == 'C' and y_zone == 'S': return 'S'
    if x_zone == 'E' and y_zone == 'C': return 'E'
    if x_zone == 'W' and y_zone == 'C': return 'W'
    
    return 'UNKNOWN'

def get_zone_coverage(x: float, y: float, w: float, d: float, plot_width: float, plot_depth: float) -> Dict[str, float]:
    """
    Calculate the proportion of the room's footprint inside each Vastu zone.
    Returns a dictionary of {zone_name: coverage_ratio}.
    """
    if plot_width <= 0 or plot_depth <= 0 or w <= 0 or d <= 0:
        return {}
        
    x1, x2 = x, x + w
    y1, y2 = y, y + d
    
    grid_x = [0.0, plot_width * ZONE_THRESHOLDS["low"], plot_width * ZONE_THRESHOLDS["high"], plot_width]
    grid_y = [0.0, plot_depth * ZONE_THRESHOLDS["low"], plot_depth * ZONE_THRESHOLDS["high"], plot_depth]
    
    x_labels = ['W', 'C', 'E']
    y_labels = ['N', 'C', 'S']
    
    room_area = w * d
    coverage = {}
    
    for i in range(3):
        for j in range(3):
            cell_x1, cell_x2 = grid_x[i], grid_x[i+1]
            cell_y1, cell_y2 = grid_y[j], grid_y[j+1]
            
            # Intersection
            ix1, ix2 = max(x1, cell_x1), min(x2, cell_x2)
            iy1, iy2 = max(y1, cell_y1), min(y2, cell_y2)
            
            if ix1 < ix2 and iy1 < iy2:
                intersect_area = (ix2 - ix1) * (iy2 - iy1)
                
                xl = x_labels[i]
                yl = y_labels[j]
                
                zone_name = 'UNKNOWN'
                if xl == 'C' and yl == 'C': zone_name = 'CENTER'
                elif xl == 'W' and yl == 'N': zone_name = 'NW'
                elif xl == 'E' and yl == 'N': zone_name = 'NE'
                elif xl == 'W' and yl == 'S': zone_name = 'SW'
                elif xl == 'E' and yl == 'S': zone_name = 'SE'
                elif xl == 'C' and yl == 'N': zone_name = 'N'
                elif xl == 'C' and yl == 'S': zone_name = 'S'
                elif xl == 'E' and yl == 'C': zone_name = 'E'
                elif xl == 'W' and yl == 'C': zone_name = 'W'
                
                coverage[zone_name] = intersect_area / room_area
                
    return coverage
