from shapely.geometry import box
from shapely.ops import unary_union

def evaluate_space_utilization(floorplan, target_ratio=0.8):
    plot_w = floorplan.plot_width
    plot_d = floorplan.plot_depth
    plot_area = plot_w * plot_d
    
    room_polygons = []
    occupied_building_area = 0
    parking_area = 0
    building_polygons = []
    
    for room in floorplan.rooms:
        poly = box(room.x, room.y, room.x + room.width, room.y + room.depth)
        room_polygons.append(poly)
        if room.type == 'parking':
            parking_area += poly.area
        else:
            occupied_building_area += poly.area
            building_polygons.append(poly)
            
    # Calculate footprints
    footprint = unary_union(building_polygons)
    building_footprint_area = footprint.area
    
    # Building Envelope (Convex Hull)
    if not footprint.is_empty:
        envelope_poly = footprint.convex_hull
        building_envelope_area = envelope_poly.area
        bbox = footprint.bounds # minx, miny, maxx, maxy
        bbox_poly = box(*bbox)
        building_bbox_area = bbox_poly.area
    else:
        envelope_poly = footprint
        building_envelope_area = 0
        building_bbox_area = 0
        bbox_poly = footprint
        
    # Calculate contiguity (number of components)
    building_components = 1
    if footprint.geom_type == 'MultiPolygon':
        building_components = len(footprint.geoms)
        
    target_buildable_area = plot_area - parking_area
    
    # Calculate space utilization score
    space_utilization = min(1.0, building_footprint_area / target_buildable_area) if target_buildable_area > 0 else 0
    space_utilization_score = space_utilization * 100
    
    # Internal voids (regions inside the building envelope that are not built)
    unused_interior_area = 0
    largest_unused_region = 0
    unused_region_count = 0
    unused_regions_details = []
    unused_regions_perimeter = 0
    
    if not envelope_poly.is_empty:
        unused_spaces = envelope_poly.difference(footprint)
        if not unused_spaces.is_empty:
            if unused_spaces.geom_type == 'Polygon':
                regions = [unused_spaces]
            elif unused_spaces.geom_type == 'MultiPolygon':
                regions = list(unused_spaces.geoms)
            else:
                regions = []
                
            for i, region in enumerate(regions):
                unused_interior_area += region.area
                unused_regions_perimeter += region.length
                largest_unused_region = max(largest_unused_region, region.area)
                unused_region_count += 1
                unused_regions_details.append({
                    "id": f"void_{i+1}",
                    "area": region.area,
                    "perimeter": region.length,
                    "type": "internal_void",
                    "bbox": list(region.bounds)
                })
                
    # Calculate compactness (shared walls)
    shared_wall_length = 0
    for i, r1 in enumerate(floorplan.rooms):
        p1 = box(r1.x, r1.y, r1.x + r1.width, r1.y + r1.depth)
        for j, r2 in enumerate(floorplan.rooms):
            if i < j:
                p2 = box(r2.x, r2.y, r2.x + r2.width, r2.y + r2.depth)
                intersection = p1.intersection(p2)
                if intersection.geom_type == 'LineString':
                    shared_wall_length += intersection.length
                elif intersection.geom_type == 'MultiLineString':
                    shared_wall_length += sum(line.length for line in intersection.geoms)
                    
    envelope_coverage_ratio = (building_footprint_area / building_envelope_area) * 100 if building_envelope_area > 0 else 0
    unused_buildable_area = max(0, plot_area - (building_footprint_area + parking_area))
    
    compactness = (building_footprint_area / building_bbox_area * 100) if building_bbox_area > 0 else 0
    
    total_perimeter = sum((room.width * 2 + room.depth * 2) for room in floorplan.rooms if room.type != 'parking')
    shared_wall_ratio = (shared_wall_length * 2 / total_perimeter * 100) if total_perimeter > 0 else 0
    
    # Gap fragmentation calculations
    average_unused_region_size = unused_interior_area / unused_region_count if unused_region_count > 0 else 0
    perimeter_to_area_ratio = unused_regions_perimeter / unused_interior_area if unused_interior_area > 0 else 0
    
    gap_penalty = unused_interior_area * 0.5
    fragmentation_penalty = (unused_region_count * 15) + (perimeter_to_area_ratio * 10)
    
    concavity_penalty = (building_envelope_area - building_footprint_area) * 0.2
    compactness_score = max(0, min(100, compactness - (building_components - 1)*20 - concavity_penalty/10 - fragmentation_penalty/5))
    
    # Define packing status properly based on void tolerances
    VOID_TOLERANCE = 10.0 # sq ft
    if unused_interior_area <= VOID_TOLERANCE and unused_region_count == 0:
        packing_status = "FULLY_PACKED"
    elif unused_interior_area <= VOID_TOLERANCE * 5:
        packing_status = "HIGHLY_PACKED"
    elif envelope_coverage_ratio >= 70:
        packing_status = "PARTIALLY_PACKED"
    else:
        packing_status = "OPEN_LAYOUT"
        
    # Room size balance score
    # Penalize extreme differences in generated room sizes of the same type
    room_areas_by_type = {}
    for r in floorplan.rooms:
        if r.type == 'parking': continue
        room_areas_by_type.setdefault(r.type, []).append(r.width * r.depth)
        
    balance_penalty = 0
    for rtype, areas in room_areas_by_type.items():
        if len(areas) > 1:
            max_area = max(areas)
            min_area = min(areas)
            if min_area > 0 and max_area / min_area > 1.5:
                # Penalty for > 50% difference between same-type rooms
                balance_penalty += min(20, (max_area / min_area - 1.5) * 10)
                
    room_balance_score = max(0, 100 - balance_penalty)

        
    plot_coverage = ((building_footprint_area + parking_area) / plot_area) if plot_area > 0 else 0
    room_coverage = (building_footprint_area / target_buildable_area) if target_buildable_area > 0 else 0

    # Evaluate metric invariants
    tol = 0.1
    inv_failures = []
    if building_footprint_area < 0:
        inv_failures.append({"rule": "footprint_area >= 0", "value": building_footprint_area})
    if building_envelope_area < building_footprint_area - tol:
        inv_failures.append({"rule": "envelope_area >= footprint_area", "envelope_area": building_envelope_area, "footprint_area": building_footprint_area})
    if building_bbox_area < building_envelope_area - tol:
        inv_failures.append({"rule": "bbox_area >= envelope_area", "bbox_area": building_bbox_area, "envelope_area": building_envelope_area})
    if unused_interior_area < -tol:
        inv_failures.append({"rule": "internal_void_area >= 0", "internal_void_area": unused_interior_area})
    
    expected_void = building_envelope_area - building_footprint_area
    if abs(unused_interior_area - expected_void) > tol:
        inv_failures.append({
            "rule": "internal_void_area == envelope_area - footprint_area",
            "internal_void_area": unused_interior_area,
            "expected_void": expected_void,
            "difference": abs(unused_interior_area - expected_void)
        })
        
    metric_invariants = {
        "valid": len(inv_failures) == 0,
        "failures": inv_failures
    }

    return {
        "plot_area": plot_area,
        "habitable_room_area": occupied_building_area,
        "parking_area": parking_area,
        "total_occupied_area": building_footprint_area + parking_area,
        "building_footprint_area": building_footprint_area,
        "building_envelope_area": building_envelope_area,
        "building_bbox_area": building_bbox_area,
        "internal_void_area": unused_interior_area,
        "unallocated_buildable_area": unused_buildable_area,
        "largest_unused_region": largest_unused_region,
        "unused_region_count": unused_region_count,
        "plot_coverage": plot_coverage,
        "room_coverage": room_coverage,
        "space_utilization": space_utilization,
        "compactness": compactness,
        
        "building_components": building_components,
        "packing_status": packing_status,
        "unused_regions": unused_regions_details,
        "metric_invariants": metric_invariants,
        
        # Legacy fields to avoid breaking older components:
        "room_area": occupied_building_area,
        "largest_unallocated_region": largest_unused_region,
        "space_utilization_score": space_utilization_score,
        "occupied_building_area": building_footprint_area,
        "target_buildable_area": target_buildable_area,
        "unused_interior_area": unused_interior_area,
        "average_unused_region_size": average_unused_region_size,
        "perimeter_to_area_ratio": perimeter_to_area_ratio,
        "fragmentation_penalty": fragmentation_penalty,
        "compactness_score": compactness_score,
        "room_balance_score": room_balance_score,
        "shared_wall_length": shared_wall_length,
        "gap_penalty": gap_penalty,
        "room_expansion_used": True,
        "building_footprint_compact": packing_status in ["FULLY_PACKED", "HIGHLY_PACKED"],
        "envelope_coverage_ratio": envelope_coverage_ratio,
        "footprint_bbox_area": building_bbox_area,
        "shared_wall_ratio": shared_wall_ratio
    }
