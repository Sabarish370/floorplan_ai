from shapely.geometry import box

def boxes_intersect(r1, r2, tolerance=0.1):
    # Create slightly smaller boxes to allow edges to touch without intersecting
    b1 = box(r1['x'] + tolerance, r1['y'] + tolerance, r1['x'] + r1['width'] - tolerance, r1['y'] + r1['depth'] - tolerance)
    b2 = box(r2['x'] + tolerance, r2['y'] + tolerance, r2['x'] + r2['width'] - tolerance, r2['y'] + r2['depth'] - tolerance)
    return b1.intersects(b2)

def boxes_touch(r1, r2, tolerance=0.1):
    b1 = box(r1['x'], r1['y'], r1['x'] + r1['width'], r1['y'] + r1['depth'])
    b2 = box(r2['x'], r2['y'], r2['x'] + r2['width'], r2['y'] + r2['depth'])
    return b1.touches(b2) or (b1.distance(b2) < tolerance)

def get_shared_edge(r1, r2):
    b1 = box(r1['x'], r1['y'], r1['x'] + r1['width'], r1['y'] + r1['depth'])
    b2 = box(r2['x'], r2['y'], r2['x'] + r2['width'], r2['y'] + r2['depth'])
    intersection = b1.intersection(b2)
    if intersection.is_empty or intersection.geom_type not in ['LineString', 'MultiLineString']:
        return None
    
    # Simple line
    bounds = intersection.bounds
    if not bounds:
        return None
        
    return {
        'x1': bounds[0],
        'y1': bounds[1],
        'x2': bounds[2],
        'y2': bounds[3]
    }
