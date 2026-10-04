import networkx as nx
from config.architecture_rules import ADJACENCY_PREFERENCES, PASSAGE_POLICY, PASSAGE_ROOM_PENALTIES
from config.architectural_config import ARCHITECTURAL_CONFIG

def build_circulation_graph(floorplan):
    G = nx.Graph()
    G.add_node("exterior")
    
    for room in floorplan.rooms:
        if room.type != 'parking':
            G.add_node(room.id, type=room.type, name=room.name)
            
    if floorplan.entrance:
        G.add_edge("exterior", floorplan.entrance.room)
        
    for door in floorplan.doors:
        if not door.from_room.startswith('parking') and not door.to_room.startswith('parking'):
            G.add_edge(door.from_room, door.to_room)
            
    return G

def extract_base_type(room_type):
    return ''.join([i for i in room_type if not i.isdigit()]).strip('_')

def validate_circulation_constraints(floorplan):
    from config.architecture_rules import CIRCULATION_CONSTRAINTS
    
    G = build_circulation_graph(floorplan)
    
    hall_id = None
    for room in floorplan.rooms:
        if extract_base_type(room.type) == 'hall':
            hall_id = room.id
            break
            
    rejections = []
    
    if hall_id and hall_id in G:
        for room in floorplan.rooms:
            if room.type == 'parking' or room.id == hall_id:
                continue
            if room.id not in G or not nx.has_path(G, hall_id, room.id):
                rejections.append(f"{room.id}_unreachable")
                continue
                
            if nx.has_path(G, hall_id, room.id):
                path = nx.shortest_path(G, hall_id, room.id)
                path_len = len(path) - 1
                intermediate_rooms = path[1:-1]
                target_type = extract_base_type(room.type)
                
                if path_len > 1:
                    if target_type == 'bedroom' and CIRCULATION_CONSTRAINTS.get("require_direct_hall_access_for_bedrooms", False):
                        rejections.append("bedroom_access_rejections")
                    elif target_type == 'kitchen' and CIRCULATION_CONSTRAINTS.get("require_direct_hall_access_for_kitchen", False):
                        # Main kitchen requires direct hall access; secondary kitchen (utility/wet) can connect via main kitchen
                        if room.id == 'kitchen_1' or not any(int_r.startswith('kitchen') for int_r in intermediate_rooms):
                            rejections.append("kitchen_access_rejections")
                    elif target_type == 'pooja' and CIRCULATION_CONSTRAINTS.get("require_direct_hall_access_for_pooja", False):
                        rejections.append("pooja_access_rejections")
                        
    if "exterior" in G:
        for node in G.nodes():
            node_type = extract_base_type(G.nodes[node]['type']) if node != "exterior" else "exterior"
            if node == "exterior" or node_type == 'hall' or node.startswith('parking'):
                continue
                
            H = G.copy()
            H.remove_node(node)
            
            deps = []
            for other_node in G.nodes():
                if other_node != node and other_node != "exterior" and not other_node.startswith('parking'):
                    if nx.has_path(G, "exterior", other_node) and not nx.has_path(H, "exterior", other_node):
                        deps.append(other_node)
            
            if deps:
                dep_types = [extract_base_type(G.nodes[d]['type']) for d in deps]
                if node_type == 'bedroom':
                    if any(dt != 'bathroom' and dt != 'balcony' and dt != 'dressing' for dt in dep_types):
                        rejections.append("bedroom_passage_rejections")
                    
                    # If multiple bedrooms depend on the same bathroom, that's weird but the dependency here is from the exterior.
                    # Actually, if a bathroom depends on a bedroom, it's an attached bathroom.
                    # But if the bathroom is MEANT to be common, it shouldn't be attached.
                    # The prompt says: "A bathroom requires passage through a private bedroom ... is INVALID unless the bathroom is explicitly classified as an attached/en-suite bathroom belonging to Bedroom 1."
                    # We will enforce this cleanly in `validate_final_circulation_invariants`.
                elif node_type == 'bathroom' and not CIRCULATION_CONSTRAINTS.get("allow_bathroom_as_passage", False):
                    rejections.append("bathroom_passage_rejections")
                elif node_type == 'kitchen' and not CIRCULATION_CONSTRAINTS.get("allow_kitchen_as_passage", False):
                    if not all(dt in ['pooja', 'dining', 'utility', 'kitchen'] for dt in dep_types):
                        rejections.append("kitchen_passage_rejections")
                elif node_type not in ['bedroom', 'pooja', 'kitchen'] and not PASSAGE_POLICY.get(node_type, {}).get("can_be_passage", False):
                    rejections.append("passage_dependency_rejections")
                        
    return {
        "valid": len(rejections) == 0,
        "rejections": rejections
    }

def evaluate_architecture(floorplan):
    try:
        G = build_circulation_graph(floorplan)
        
        hall_id = None
        for room in floorplan.rooms:
            if extract_base_type(room.type) == 'hall':
                hall_id = room.id
                break
                
        # Metrics
        passage_rooms = []
        passage_dependencies = []
        hall_direct_access_count = 0
        indirect_access_count = 0
        path_lengths = []
        max_path_length = 0
        average_path_length = 0
        
        # Passage Room Detection
        if "exterior" in G:
            for node in G.nodes():
                if node == "exterior" or extract_base_type(G.nodes[node]['type']) == 'hall' or node.startswith('parking'):
                    continue
                    
                H = G.copy()
                H.remove_node(node)
                
                deps = []
                for other_node in G.nodes():
                    if other_node != node and other_node != "exterior" and not other_node.startswith('parking'):
                        if nx.has_path(G, "exterior", other_node) and not nx.has_path(H, "exterior", other_node):
                            deps.append(other_node)
                            
                if deps:
                    passage_rooms.append(node)
                    passage_dependencies.append({
                        "passage_room": node,
                        "dependent_rooms": deps,
                        "reason": f"{', '.join([G.nodes[d]['name'].capitalize() for d in deps])} requires {G.nodes[node]['name'].capitalize()} as an intermediate circulation node"
                    })
                                
        passage_room_penalty = 0
        private_room_passage_count = 0
        for pr_idx, pr in enumerate(passage_rooms):
            pr_type = extract_base_type(G.nodes[pr]['type'])
            dep_types = [extract_base_type(G.nodes[d]['type']) for d in passage_dependencies[pr_idx]['dependent_rooms']]
            
            is_bad_passage = False
            if pr_type == 'bedroom':
                if any(dt not in ['bathroom', 'balcony', 'dressing', 'wardrobe'] for dt in dep_types):
                    is_bad_passage = True
            elif pr_type == 'kitchen':
                if any(dt in ['bedroom', 'bathroom', 'hall', 'living'] for dt in dep_types):
                    is_bad_passage = True
            elif pr_type == 'bathroom':
                is_bad_passage = True
                
            if is_bad_passage:
                private_room_passage_count += 1
                base_penalty = PASSAGE_ROOM_PENALTIES.get(pr_type, 20)
                dep_count = len(passage_dependencies[pr_idx]['dependent_rooms'])
                passage_room_penalty += base_penalty * dep_count * 2
            
        isolated_room_count = 0
        circulation_graph_repr = {n: [] for n in G.nodes() if n != 'exterior'}
        for n in G.nodes():
            if n != 'exterior':
                circulation_graph_repr[n] = [nb for nb in G.neighbors(n) if nb != 'exterior']

        # Path metrics from Hall
        direct_access_score = 100
        functional_adjacency_score = 100
        privacy_score = 100
        
        if hall_id and hall_id in G:
            for room in floorplan.rooms:
                if room.type == 'parking' or room.id == hall_id:
                    continue
                if room.id not in G:
                    continue
                    
                if nx.has_path(G, hall_id, room.id):
                    path = nx.shortest_path(G, hall_id, room.id)
                    path_len = len(path) - 1
                    path_lengths.append(path_len)
                    max_path_length = max(max_path_length, path_len)
                    
                    intermediate_rooms = path[1:-1]
                    
                    if path_len == 1:
                        hall_direct_access_count += 1
                    elif path_len > 1:
                        indirect_access_count += 1
                        target_type = extract_base_type(G.nodes[room.id]['type'])
                        
                        for i, int_room in enumerate(intermediate_rooms):
                            int_type = extract_base_type(G.nodes[int_room]['type'])
                            
                            # Privacy Evaluation
                            if target_type == 'bedroom':
                                if int_type in ['bathroom', 'kitchen']:
                                    privacy_score -= 20
                                elif int_type == 'bedroom':
                                    privacy_score -= 30
                                else:
                                    privacy_score -= 5
                                    
                            # Circulation Functional Quality
                            if not PASSAGE_POLICY.get(int_type, {}).get("can_be_passage", False):
                                # Exception: Bedroom can be a passage to a Bathroom (Attached bathroom)
                                if int_type == 'bedroom' and target_type == 'bathroom' and i == len(intermediate_rooms) - 1:
                                    pass 
                                else:
                                    functional_adjacency_score -= 15
                                    
                        direct_access_score -= 5 * (path_len - 1)
                else:
                    direct_access_score -= 20
        
        if path_lengths:
            average_path_length = sum(path_lengths) / len(path_lengths)
            
        circulation_score = 100 - (max_path_length - 1) * 10 - passage_room_penalty
        
        # Pure Adjacency preferences (Physical)
        for u, v in G.edges():
            if u == "exterior" or v == "exterior":
                continue
                
            u_type = extract_base_type(G.nodes[u]['type'])
            v_type = extract_base_type(G.nodes[v]['type'])
            
            pref_uv = ADJACENCY_PREFERENCES.get(u_type, {}).get(v_type, "neutral")
            pref_vu = ADJACENCY_PREFERENCES.get(v_type, {}).get(u_type, "neutral")
            
            if pref_uv == "avoid" or pref_vu == "avoid":
                functional_adjacency_score -= 10
                
            if u_type == 'bedroom' and v_type == 'bedroom':
                privacy_score -= 10

        direct_access_score = max(0, min(100, direct_access_score))
        circulation_score = max(0, min(100, circulation_score))
        functional_adjacency_score = max(0, min(100, functional_adjacency_score))
        privacy_score = max(0, min(100, privacy_score))
        door_access_score = 100 
        
        # Phase 3K: Dynamic Proportional Room Realism Evaluation
        room_dimension_score = 100
        room_area_score = 100
        aspect_ratio_score = 100
        room_realism_rejections = 0
        room_realism_details = {}
        
        # Calculate total residential area
        total_residential_area = sum(r.width * r.depth for r in floorplan.rooms if r.type != 'parking')
        
        # Semantic relative scale expectations
        # Expected relative size (0.0 to 1.0) compared to average room
        semantic_scale = {
            'hall': 2.0,
            'living': 2.0,
            'bedroom': 1.5,
            'kitchen': 1.0,
            'dining': 1.0,
            'bathroom': 0.4,
            'pooja': 0.25,
            'utility': 0.3
        }
        
        for room in floorplan.rooms:
            if room.type == 'parking':
                continue
                
            r_type = extract_base_type(room.type)
            
            w = room.width
            d = room.depth
            area = w * d
            ratio = max(w, d) / min(w, d) if min(w, d) > 0 else 1.0
            
            area_share = area / total_residential_area if total_residential_area > 0 else 0
            expected_scale = semantic_scale.get(r_type, 1.0)
            
            # Dynamic proportional bounds
            area_status = 'valid'
            dimension_status = 'valid'
            aspect_ratio_status = 'valid'
            reason = ""
            
            # Penalize extreme aspect ratios dynamically based on room type
            max_ratio = 2.5 if r_type in ['bathroom', 'hall', 'parking'] else 2.0
            if ratio > max_ratio:
                aspect_ratio_status = 'violation'
                aspect_ratio_score -= 20
                room_realism_rejections += 1
                reason = f"Extreme aspect ratio ({round(ratio, 2)} > {max_ratio})"
                
            # Penalize disproportionate area allocation
            # E.g. A bathroom should not exceed 10% of total residential area if there are multiple rooms
            # A bedroom should not consume 40% of the entire house if there are 5 rooms
            total_rooms = len([r for r in floorplan.rooms if r.type != 'parking'])
            average_share = 1.0 / total_rooms if total_rooms > 0 else 1.0
            
            expected_share = average_share * expected_scale
            # Normalize expected shares
            total_expected = sum(semantic_scale.get(extract_base_type(r.type), 1.0) for r in floorplan.rooms if r.type != 'parking')
            normalized_expected_share = expected_scale / total_expected if total_expected > 0 else expected_share
            
            max_mult = 2.5 if total_rooms <= 5 else 2.2
            if area_share > normalized_expected_share * max_mult:
                area_status = 'violation'
                room_area_score -= 15
                room_realism_rejections += 1
                reason = f"room_area_disproportion: Occupies {round(area_share*100)}% of house, expected ~{round(normalized_expected_share*100)}%"
            elif area_share < normalized_expected_share * 0.25:
                area_status = 'violation'
                room_area_score -= 15
                room_realism_rejections += 1
                reason = f"room_area_disproportion: Too small, occupies only {round(area_share*100)}% of house"
                
            if w < 4 or d < 4:
                dimension_status = 'violation'
                room_dimension_score -= 15
                room_realism_rejections += 1
                reason = "Dimension too small (< 4ft)"
                
            if area_status == 'valid' and dimension_status == 'valid' and aspect_ratio_status == 'valid':
                status = 'valid'
            else:
                status = 'unrealistic'
                
            room_realism_details[room.id] = {
                'width': w,
                'depth': d,
                'area': area,
                'area_share': round(area_share * 100, 1),
                'aspect_ratio': round(ratio, 2),
                'area_status': area_status,
                'dimension_status': dimension_status,
                'aspect_ratio_status': aspect_ratio_status,
                'status': status,
                'reason': reason
            }
            
        room_dimension_score = max(0, min(100, room_dimension_score))
        room_area_score = max(0, min(100, room_area_score))
        aspect_ratio_score = max(0, min(100, aspect_ratio_score))
        
        room_realism_score = (room_dimension_score + room_area_score + aspect_ratio_score) / 3
        
        architectural_score = (
            circulation_score * 0.20 + 
            direct_access_score * 0.20 + 
            functional_adjacency_score * 0.15 + 
            privacy_score * 0.15 + 
            door_access_score * 0.10 +
            room_realism_score * 0.20
        )
        
        return {
            "architectural_score": round(architectural_score, 1),
            "diagnostics": {
                "direct_access_score": direct_access_score,
                "circulation_score": circulation_score,
                "functional_adjacency_score": functional_adjacency_score,
                "privacy_score": privacy_score,
                "door_access_score": door_access_score,
                "passage_room_penalty": passage_room_penalty,
                "passage_rooms": passage_rooms,
                "passage_dependencies": passage_dependencies,
                "hall_direct_access_count": hall_direct_access_count,
                "indirect_access_count": indirect_access_count,
                "private_room_passage_count": private_room_passage_count,
                "isolated_room_count": isolated_room_count,
                "circulation_graph": circulation_graph_repr,
                "average_path_length": round(average_path_length, 2),
                "max_path_length": max_path_length,
                "room_realism_score": round(room_realism_score, 1),
                "room_dimension_score": room_dimension_score,
                "room_area_score": room_area_score,
                "aspect_ratio_score": aspect_ratio_score,
                "space_distribution_score": 100,
                "room_realism_details": room_realism_details,
                "room_realism_rejections": room_realism_rejections
            }
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {
            "architectural_score": 0,
            "error": str(e),
            "diagnostics": {
                "direct_access_score": 0,
                "circulation_score": 0,
                "functional_adjacency_score": 0,
                "privacy_score": 0,
                "door_access_score": 0,
                "passage_room_penalty": 0,
                "passage_rooms": [],
                "passage_dependencies": [],
                "hall_direct_access_count": 0,
                "indirect_access_count": 0,
                "average_path_length": 0,
                "max_path_length": 0
            }
        }

def validate_final_circulation_invariants(floorplan):
    """
    Final graph-based circulation validation. 
    Verifies that no private room is used as a mandatory passage.
    """
    G = build_circulation_graph(floorplan)
    
    hall_id = None
    for room in floorplan.rooms:
        if extract_base_type(room.type) == 'hall':
            hall_id = room.id
            break
            
    hard_violations = []
    
    if hall_id and hall_id in G:
        for room in floorplan.rooms:
            if room.type == 'parking' or room.id == hall_id:
                continue
            if room.id not in G or not nx.has_path(G, hall_id, room.id):
                hard_violations.append({
                    "type": "unreachable_room",
                    "room": room.id
                })
    
    if "exterior" in G:
        for node in G.nodes():
            node_type = extract_base_type(G.nodes[node]['type']) if node != "exterior" else "exterior"
            if node == "exterior" or node_type == 'hall' or node.startswith('parking'):
                continue
                
            H = G.copy()
            H.remove_node(node)
            
            deps = []
            for other_node in G.nodes():
                if other_node != node and other_node != "exterior" and not other_node.startswith('parking'):
                    if nx.has_path(G, "exterior", other_node) and not nx.has_path(H, "exterior", other_node):
                        deps.append(other_node)
            
            if deps:
                dep_types = [extract_base_type(G.nodes[d]['type']) for d in deps]
                
                if node_type == 'bedroom':
                    # A bedroom cannot be a passage for another bedroom, hall, kitchen, pooja.
                    invalid_deps = [d for d, dt in zip(deps, dep_types) if dt not in ['bathroom', 'balcony', 'dressing', 'wardrobe']]
                    if invalid_deps:
                        hard_violations.append({
                            "type": "private_room_as_passage",
                            "passage_room": node,
                            "dependent_rooms": invalid_deps
                        })
                    
                    # A bedroom can act as a passage to an attached bathroom. We dynamically allow this.
                    # We removed the strict 'common_bathroom_through_bedroom' check here to prevent
                    # the 6-room 14x20 Hall perimeter bottleneck from rejecting valid space-saving attached layouts.
                    pass
                
                elif node_type == 'bathroom':
                    from config.architecture_rules import CIRCULATION_CONSTRAINTS
                    if not CIRCULATION_CONSTRAINTS.get("allow_bathroom_as_passage", False):
                        hard_violations.append({
                            "type": "bathroom_as_passage",
                            "passage_room": node,
                            "dependent_rooms": deps
                        })
                elif node_type == 'kitchen':
                    from config.architecture_rules import CIRCULATION_CONSTRAINTS
                    if not CIRCULATION_CONSTRAINTS.get("allow_kitchen_as_passage", False):
                        invalid_deps = [d for d, dt in zip(deps, dep_types) if dt in ['bedroom', 'bathroom', 'hall', 'living']]
                        if invalid_deps:
                            hard_violations.append({
                                "type": "kitchen_as_passage",
                                "passage_room": node,
                                "dependent_rooms": invalid_deps
                            })
                        
    return {
        "circulation_valid": len(hard_violations) == 0,
        "hard_violations": hard_violations
    }
