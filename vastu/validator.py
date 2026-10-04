from typing import List, Dict, Any, Tuple
from models.floorplan import FloorPlan
from vastu.zones import get_zone, get_zone_coverage
from vastu.rules import VASTU_RULES
from vastu.scorer import calculate_vastu_score
import re

def normalize_room_type(name: str) -> str:
    """Normalize room name to map to rules."""
    name = name.lower()
    if 'bedroom' in name:
        if 'master' in name: return 'master_bedroom'
        return 'bedroom'
    if 'bath' in name or 'toilet' in name: return 'bathroom'
    if 'pooja' in name or 'puja' in name: return 'pooja'
    if 'kitchen' in name: return 'kitchen'
    if 'hall' in name or 'living' in name: return 'hall'
    if 'parking' in name or 'garage' in name: return 'parking'
    if 'dining' in name: return 'dining'
    return name

def analyze_vastu(plan: FloorPlan) -> Dict[str, Any]:
    """
    Analyze an existing FloorPlan against Vastu rules.
    """
        # 1. Calculate zones for each room
    room_zones = {}
    
    # Process regular rooms
    for room in plan.rooms:
        coverage = get_zone_coverage(room.x, room.y, room.width, room.depth, plan.plot_width, plan.plot_depth)
        
        # Primary zone is the one with the maximum coverage
        primary_zone = max(coverage.items(), key=lambda x: x[1])[0] if coverage else "UNKNOWN"
        
        r_type = normalize_room_type(room.type)
        rule = next((r for r in VASTU_RULES if r['room_type'] == r_type), None)
        
        p_zones = rule.get('preferred_zones', []) if rule else []
        a_zones = rule.get('acceptable_zones', []) if rule else []
        av_zones = rule.get('avoid_zones', []) if rule else []
        
        p_cov = sum(cov for z, cov in coverage.items() if z in p_zones)
        a_cov = sum(cov for z, cov in coverage.items() if z in a_zones)
        av_cov = sum(cov for z, cov in coverage.items() if z in av_zones)
        n_cov = sum(cov for z, cov in coverage.items() if z not in p_zones and z not in a_zones and z not in av_zones)
        
        room_zones[room.id] = {
            "room_id": room.id,
            "name": room.name,
            "type": r_type,
            "zone": primary_zone,
            "coverage": coverage,
            "preferred_zone_coverage": p_cov,
            "acceptable_zone_coverage": a_cov,
            "avoid_zone_coverage": av_cov,
            "neutral_zone_coverage": n_cov,
            "center": {
                "x": room.x + room.width / 2,
                "y": room.y + room.depth / 2
            }
        }
        
    # Process parking if available but not in rooms list
    if hasattr(plan, 'vehicle_gate') and plan.vehicle_gate:
        # Check if parking is already in rooms list
        if not any(r.id.startswith('parking') for r in plan.rooms):
            # We don't have explicit geometry for parking in plan.rooms in some cases? 
            # In our current generator it IS in placed_rooms, so it should be in plan.rooms.
            pass
            
    # 2. Evaluate rules
    results = []
    
    for room_id, rdata in room_zones.items():
        rtype = rdata['type']
        zone = rdata['zone']
        
        # Find applicable rules
        applicable_rules = [r for r in VASTU_RULES if r['room_type'] == rtype]
        
        for rule in applicable_rules:
            result = {
                "rule_id": rule['id'],
                "room": room_id,
                "room_name": rdata['name'],
                "zone": zone,
                "preferred_zones": rule.get('preferred_zones', []),
                "acceptable_zones": rule.get('acceptable_zones', []),
                "avoid_zones": rule.get('avoid_zones', []),
                "severity": rule['severity'],
                "weight": rule['weight'],
                "message": "",
                "status": "unknown"
            }
            
            p_zones = result["preferred_zones"]
            a_zones = result["acceptable_zones"]
            av_zones = result["avoid_zones"]
            
            coverage = rdata.get('coverage', {zone: 1.0})
            intersects_avoid = any(z in av_zones for z, cov in coverage.items() if cov > 0.05) # 5% tolerance
            
            if intersects_avoid:
                intersected_zones = [z for z, cov in coverage.items() if cov > 0.05 and z in av_zones]
                if rule['severity'] == 'hard':
                    result['status'] = 'violation'
                else:
                    result['status'] = 'penalty'
                result['message'] = f"{rdata['name']} footprint intersects avoided zones ({', '.join(intersected_zones)})."
            elif av_zones and not p_zones and not a_zones:
                result['status'] = 'pass'
                result['message'] = f"{rdata['name']} is outside the configured avoided zones."
                result['p_cov'] = 1.0
                result['a_cov'] = 0.0
            else:
                p_cov = sum(cov for z, cov in coverage.items() if z in p_zones)
                a_cov = sum(cov for z, cov in coverage.items() if z in a_zones)
                
                result['p_cov'] = p_cov
                result['a_cov'] = a_cov
                
                if p_cov >= 0.05 or a_cov >= 0.05:
                    if p_cov >= a_cov:
                        result['status'] = 'preferred'
                        result['message'] = f"{rdata['name']} has {p_cov*100:.1f}% preferred and {a_cov*100:.1f}% acceptable coverage."
                    else:
                        result['status'] = 'acceptable'
                        result['message'] = f"{rdata['name']} has {a_cov*100:.1f}% acceptable and {p_cov*100:.1f}% preferred coverage."
                else:
                    result['status'] = 'warning'
                    result['message'] = f"{rdata['name']} is mostly in neutral zones. Preferred: {', '.join(p_zones)}."
                    
            results.append(result)
            
    # 3. Compile report
    passed_rules = sum(1 for r in results if r['status'] in ('preferred', 'acceptable', 'pass'))
    warnings = sum(1 for r in results if r['status'] == 'warning')
    penalties = sum(1 for r in results if r['status'] == 'penalty')
    violations = sum(1 for r in results if r['status'] == 'violation')
    score = calculate_vastu_score(results)
    
    return {
        "score": score,
        "rules_checked": len(results),
        "passed": passed_rules,
        "warnings": warnings,
        "penalties": penalties,
        "violations": violations,
        "results": results,
        "room_zones": room_zones
    }
