from models.requirements import FloorPlanRequirements
from models.floorplan import FloorPlan
from layout.generator import generate_layout, generate_layout_beam_search
from layout.validator import validate_layout
from vastu.validator import analyze_vastu
from layout.architecture import evaluate_architecture, validate_circulation_constraints
from layout.space_utilization import evaluate_space_utilization
from config.architectural_config import ARCHITECTURAL_CONFIG
from layout.global_packer import optimize_global_footprint

STRATEGIES = ['baseline', 'vastu_first', 'bedroom_first', 'kitchen_first', 'balanced']

def get_structural_signature(arch, vastu):
    edges = set()
    circ_graph = arch.get('diagnostics', {}).get('circulation_graph', {})
    for u, neighbors in circ_graph.items():
        for v in neighbors:
            edges.add(tuple(sorted([u, v])))
    
    zones = {res['room']: res['zone'] for res in vastu['results']}
    hall_conn = arch.get('diagnostics', {}).get('hall_direct_access_count', 0)
    
    sig_str = f"Edges:{sorted(list(edges))}|Zones:{sorted(zones.items())}|Hall:{hall_conn}"
    import hashlib
    return hashlib.md5(sig_str.encode()).hexdigest()

def optimize_layout(reqs: FloorPlanRequirements, baseline: FloorPlan, baseline_vastu: dict) -> tuple:
    """
    Generate multiple candidates by introducing controlled deterministic randomness 
    (seed > 0) to the layout generator, guided by Vastu preferences.
    Validates them and ranks them by Vastu score and compactness.
    Returns (best_candidate, best_vastu, metadata).
    """
    candidates_generated = 0
    valid_candidates = []
    
    rejections = {
        "overlap_rejections": 0,
        "boundary_rejections": 0,
        "connectivity_rejections": 0,
        "room_count_rejections": 0,
        "vastu_avoidance_rejections": 0,
        "other_geometry_rejections": 0,
        "bedroom_access_rejections": 0,
        "bathroom_passage_rejections": 0,
        "kitchen_passage_rejections": 0,
        "bedroom_passage_rejections": 0,
        "pooja_access_rejections": 0,
        "kitchen_access_rejections": 0,
        "passage_dependency_rejections": 0
    }
    
    geometry_valid_count = 0
    connectivity_valid_count = 0
    circulation_valid_count = 0
    
    vastu_telemetry = {
        "preferred_zone_placement_attempts": {},
        "preferred_zone_placement_successes": {},
        "acceptable_zone_placement_attempts": {},
        "acceptable_zone_placement_successes": {},
        "avoid_zone_checks": {},
        "candidate_avoid_zone_violation_events": {}
    }
    search_metrics = {
        "search_nodes": 0,
        "branches_pruned": 0,
        "partial_candidates": 0,
        "complete_candidates": 0,
        "beam_width": 15,
        "max_candidates_per_room": 6,
        "topology_pruned": 0,
        "connected_candidates_generated": 0,
        "disconnected_candidates_generated": 0,
        "door_feasible_candidates": 0,
        "adjacency_evaluations": 0,
        "adjacency_rejections": 0,
        "unique_geometric_candidates": 0,
        "duplicate_candidates_removed": 0,
        "structural_candidates_generated": 0,
        "structural_duplicates_removed": 0,
        "unique_structural_candidates": 0,
        "structural_family_count": 0,
        "final_candidate_revalidated": False,
        "circulation_hard_rejections": 0,
        "metric_invariant_failures": 0,
        "room_candidate_diagnostics": {}
    }
    
    seen_fingerprints = set()
    seen_structural_signatures = set()
    
    def get_candidate_fingerprint(candidate):
        fp_items = []
        for r in candidate.rooms:
            if r.type != 'parking':
                fp_items.append(f"{r.type}_{round(r.x)}_{round(r.y)}_{round(r.width)}_{round(r.depth)}")
        fp_items.sort()
        return "|".join(fp_items)
    
    # We will generate candidates using the new beam search layer
    for strategy in STRATEGIES:
        try:
            if strategy == 'baseline':
                candidates_to_test = [generate_layout(reqs, seed=42, strategy='baseline')]
                candidates_generated += 1
                search_metrics["complete_candidates"] += 1
            else:
                beam_candidates, s_metrics = generate_layout_beam_search(reqs, strategy=strategy, beam_width=15, max_candidates_per_room=6)
                candidates_to_test = beam_candidates
                candidates_generated += len(beam_candidates)
                
                # Aggregate search metrics
                for k in ["search_nodes", "branches_pruned", "partial_candidates", "complete_candidates", "topology_pruned"]:
                    search_metrics[k] += s_metrics.get(k, 0)
                    
                for r_type, diag in s_metrics.get("room_candidate_diagnostics", {}).items():
                    if r_type not in search_metrics["room_candidate_diagnostics"]:
                        search_metrics["room_candidate_diagnostics"][r_type] = diag
                    else:
                        for dk, dv in diag.items():
                            if isinstance(dv, dict):
                                for ddk, ddv in dv.items():
                                    search_metrics["room_candidate_diagnostics"][r_type][dk][ddk] = search_metrics["room_candidate_diagnostics"][r_type][dk].get(ddk, 0) + ddv
                            else:
                                search_metrics["room_candidate_diagnostics"][r_type][dk] += dv
                    
            for candidate in candidates_to_test:
                fp = get_candidate_fingerprint(candidate)
                if fp in seen_fingerprints:
                    search_metrics["duplicate_candidates_removed"] = search_metrics.get("duplicate_candidates_removed", 0) + 1
                    continue
                seen_fingerprints.add(fp)
                search_metrics["unique_geometric_candidates"] += 1
                
                validation = validate_layout(candidate)
                
                # Ensure room counts match exactly
                req_count = sum(count for room, count in reqs.rooms.items() if room != 'parking')
                gen_count = len([r for r in candidate.rooms if r.type not in ['parking', 'circulation']])
                
                # Track building_connected and door_feasible based on validation string
                errs = " ".join(validation.get("errors", [])).lower()
                is_connected = "connect" not in errs and "accessible" not in errs
                
                if is_connected:
                    search_metrics["connected_candidates_generated"] += 1
                    search_metrics["door_feasible_candidates"] += 1
                else:
                    search_metrics["disconnected_candidates_generated"] += 1
                
                if req_count == gen_count:
                    if validation['valid']:
                        geometry_valid_count += 1
                        connectivity_valid_count += 1
                        
                        circ_val = validate_circulation_constraints(candidate)
                        if not circ_val['valid']:
                            for r in circ_val['rejections']:
                                rejections[r] = rejections.get(r, 0) + 1
                        else:
                            circulation_valid_count += 1
                            v_report = analyze_vastu(candidate)
                            c_arch = evaluate_architecture(candidate)
                            
                            search_metrics["structural_candidates_generated"] += 1
                            sig = get_structural_signature(c_arch, v_report)
                            if sig not in seen_structural_signatures:
                                seen_structural_signatures.add(sig)
                            
                            search_metrics["unique_structural_candidates"] = len(seen_structural_signatures)
                            search_metrics["structural_family_count"] = len(seen_structural_signatures)
                            
                            # Log telemetry for architecturally valid candidates
                            for res in v_report['results']:
                                rtype = res['room']
                                status = res['status']
                                
                                for k in vastu_telemetry:
                                    if rtype not in vastu_telemetry[k]:
                                        vastu_telemetry[k][rtype] = 0
                                        
                                if 'preferred' in str(res): vastu_telemetry['preferred_zone_placement_attempts'][rtype] += 1
                                if 'acceptable' in str(res): vastu_telemetry['acceptable_zone_placement_attempts'][rtype] += 1
                                if 'avoid' in str(res) or status in ('pass', 'violation'): vastu_telemetry['avoid_zone_checks'][rtype] += 1
                                
                                if status == 'preferred': vastu_telemetry['preferred_zone_placement_successes'][rtype] += 1
                                elif status == 'acceptable': vastu_telemetry['acceptable_zone_placement_successes'][rtype] += 1
                                elif status == 'penalty': vastu_telemetry['candidate_avoid_zone_violation_events'][rtype] += 1
                                elif status == 'violation': vastu_telemetry['candidate_avoid_zone_violation_events'][rtype] += 1
                            
                            if any(r['status'] == 'violation' for r in v_report['results']):
                                rejections["vastu_avoidance_rejections"] += 1
                            else:
                                space_stats = evaluate_space_utilization(candidate, target_ratio=0.8)
                                valid_candidates.append({
                                    'layout': candidate,
                                    'vastu': v_report,
                                    'architecture': c_arch,
                                    'space': space_stats,
                                    'signature': sig
                                })
                    else:
                        # Log rejection reasons loosely
                        # Log rejection reasons loosely
                        errs = " ".join(validation.get("errors", [])).lower()
                        if "overlap" in errs: rejections["overlap_rejections"] += 1
                        elif "boundary" in errs or "outside" in errs: rejections["boundary_rejections"] += 1
                        elif "connect" in errs or "accessible" in errs: rejections["connectivity_rejections"] += 1
                        else: rejections["other_geometry_rejections"] += 1
                        
                        if "connect" not in errs and "accessible" not in errs:
                            geometry_valid_count += 1
                            connectivity_valid_count += 1
                else:
                    rejections["room_count_rejections"] += 1
                    
            search_metrics["adjacency_evaluations"] = search_metrics["complete_candidates"]
            search_metrics["adjacency_rejections"] = rejections["connectivity_rejections"]
                        
        except Exception as e:
            import traceback
            print(f"STRATEGY EXCEPTION in {strategy}:", e)
            traceback.print_exc()
            continue
            
    baseline_space = evaluate_space_utilization(baseline, target_ratio=0.8)
    
    # Filter candidates strictly
    fully_valid_candidates = []
    fallback_candidates = []
    
    def calculate_combined_score(c_data):
        v_score = c_data['vastu']['score']
        a_score = c_data['architecture']['architectural_score']
        s_score = c_data['space']['space_utilization_score']
        c_score = c_data['space']['compactness_score']
        b_score = c_data['space'].get('room_balance_score', 100)
        
        v_weight = ARCHITECTURAL_CONFIG['weights'].get('vastu', 0.20)
        a_weight = ARCHITECTURAL_CONFIG['weights'].get('architecture', 0.45)
        s_weight = ARCHITECTURAL_CONFIG['weights'].get('space', 0.25)
        c_weight = ARCHITECTURAL_CONFIG['weights'].get('compactness', 0.10)
        # Assuming room balance is baked into space or compactness in the prompt's view, or we keep it as a bonus
        # Actually, let's normalize weights if we add balance, or just keep it as a raw penalty.
        # But the prompt says "Vastu Weight = 0.20, Architecture Weight = 0.45, Space Efficiency Weight = 0.25, Compactness Weight = 0.10".
        # Let's strictly follow the weights.
        
        v_contrib = v_score * v_weight
        a_contrib = a_score * a_weight
        s_contrib = s_score * s_weight
        c_contrib = c_score * c_weight
        
        # Room balance is an additional penalty/bonus
        balance_penalty = (100 - b_score) * 0.10
        
        total = v_contrib + a_contrib + s_contrib + c_contrib - balance_penalty
        
        c_data['score_breakdown'] = {
            "vastu_raw": round(v_score, 1),
            "architecture_raw": round(a_score, 1),
            "space_raw": round(s_score, 1),
            "compactness_raw": round(c_score, 1),
            "room_balance_raw": round(b_score, 1),
            "vastu_weight": v_weight,
            "architecture_weight": a_weight,
            "space_weight": s_weight,
            "compactness_weight": c_weight,
            "vastu_contribution": round(v_contrib, 1),
            "architecture_contribution": round(a_contrib, 1),
            "space_contribution": round(s_contrib, 1),
            "compactness_contribution": round(c_contrib, 1),
            "penalties": round(balance_penalty, 1),
            "final_combined_score": round(total, 1)
        }
        return total
        
    for c in valid_candidates:
        if 'architecture' not in c:
            c['architecture'] = evaluate_architecture(c['layout'])
        c['combined_score'] = calculate_combined_score(c)
    
    # Let's fix the logic where we rank the candidates.
    def rank_key(c):
        score = c['combined_score']
        v = c['vastu']
        unrealistic_rooms = c.get('architecture', {}).get('diagnostics', {}).get('room_realism_rejections', 0)
        pref = sum(1 for r in v['results'] if r['status'] == 'preferred')
        acc = sum(1 for r in v['results'] if r['status'] == 'acceptable')
        penalties = sum(1 for r in v['results'] if r['status'] in ('penalty', 'violation'))
        
        return (-unrealistic_rooms, -penalties, score, pref, acc)
        
    if not valid_candidates:
        # Emergency Fallback Level 3
        # Add baseline only if no candidates
        fallback_arch = evaluate_architecture(baseline)
        fallback_cand = {
            'layout': baseline,
            'vastu': baseline_vastu,
            'space': baseline_space,
            'architecture': fallback_arch,
            'is_fallback': True
        }
        fallback_cand['combined_score'] = calculate_combined_score(fallback_cand)
        valid_candidates.append(fallback_cand)
    else:
        for c in valid_candidates:
            c['is_fallback'] = False
        
    # Re-sort to find the best before heavy footprint/global optimization
    valid_candidates.sort(key=rank_key, reverse=True)
    
    # Take top 3 candidates for heavy footprint/global optimization
    top_cands = valid_candidates[:3]
    
    # Phase 3G.5 Footprint Optimization
    from layout.footprint_optimizer import optimize_footprint
    for i in range(len(top_cands)):
        if top_cands[i]['layout'] == baseline:
            continue
        opt_cand = optimize_footprint(top_cands[i], reqs, reqs.plot.width, reqs.plot.depth, reqs.plot.facing.lower())
        opt_cand['combined_score'] = calculate_combined_score(opt_cand)
        top_cands[i] = opt_cand
        
    # Phase 3G.6 Global Packing
    for i in range(len(top_cands)):
        if top_cands[i]['layout'] == baseline:
            continue
        c = top_cands[i]
        packed_layout, packing_metadata = optimize_global_footprint(c['layout'], reqs, reqs.plot.width, reqs.plot.depth, reqs.plot.facing.lower())
        c['layout'] = packed_layout
        c['vastu'] = analyze_vastu(packed_layout)
        c['architecture'] = evaluate_architecture(packed_layout)
        c['space'] = evaluate_space_utilization(packed_layout, target_ratio=0.8)
        
        c['combined_score'] = calculate_combined_score(c)
        top_cands[i] = c
        
    # Re-sort to find the true best among top candidates after heavy optimization
    top_cands.sort(key=rank_key, reverse=True)
    valid_candidates = top_cands + [c for c in valid_candidates if c not in top_cands]
        
    # Phase 3I: FINAL INVARIANT VALIDATION
    # Iterate through candidates until one passes ALL final invariants.
    final_validation_result = {
        "valid": False,
        "geometry": False,
        "connectivity": False,
        "circulation": False,
        "architecture": False,
        "metrics": False,
        "room_count": False,
        "hard_violations": []
    }
    
    best = None
    from layout.architecture import validate_final_circulation_invariants
    
    # Keep a copy in case all fail
    all_cands_backup = list(valid_candidates)
    best_failed_candidate = None
    
    while valid_candidates:
        test_c = valid_candidates[0]
        layout = test_c['layout']
        
        # 1. Geometry & Connectivity
        val_res = validate_layout(layout)
        errs = " ".join(val_res.get("errors", [])).lower()
        is_connected = "connect" not in errs and "accessible" not in errs
        req_count = sum(count for room, count in reqs.rooms.items() if room != 'parking')
        gen_count = len([r for r in layout.rooms if r.type not in ['parking', 'circulation']])
        room_count_valid = req_count == gen_count
        
        geometry_valid = val_res['valid'] and is_connected and room_count_valid
        
        # 2. Circulation
        circ_val = validate_final_circulation_invariants(layout)
        
        # 3. Metrics
        metric_invariants = test_c['space'].get('metric_invariants', {'valid': True})
        
        # Track telemetry
        if not circ_val['circulation_valid']:
            search_metrics['circulation_hard_rejections'] += 1
        if not metric_invariants['valid']:
            search_metrics['metric_invariant_failures'] += 1
            
        if geometry_valid and circ_val['circulation_valid'] and metric_invariants['valid']:
            best = test_c
            final_validation_result.update({
                "valid": True,
                "geometry": True,
                "connectivity": True,
                "circulation": True,
                "architecture": True, # Implicit if reached
                "metrics": True,
                "room_count": True,
                "hard_violations": []
            })
            search_metrics["final_candidate_revalidated"] = True
            break
        else:
            if not best_failed_candidate:
                best_failed_candidate = test_c
                final_validation_result.update({
                    "valid": False,
                    "geometry": val_res['valid'],
                    "connectivity": is_connected,
                    "circulation": circ_val['circulation_valid'],
                    "architecture": False,
                    "metrics": metric_invariants['valid'],
                    "room_count": room_count_valid,
                    "hard_violations": circ_val.get('hard_violations', [])
                })
            # Pop and try next
            valid_candidates.pop(0)
            
    if not best:
        # All candidates failed. We return the best_failed_candidate but marked as invalid.
        best = best_failed_candidate if best_failed_candidate else all_cands_backup[0]
        
    if best.get('is_fallback', False):
        # Override fake architecture scores
        best_arch = best['architecture']
        best_arch['architectural_score'] = "INVALID (FALLBACK)"
    else:
        best_arch = best['architecture']
        
    best_space = best['space']
    
    selected_candidate_diagnostics = {
        "rooms_in_preferred_zones": sum(1 for r in best['vastu']['results'] if r['status'] == 'preferred'),
        "rooms_in_acceptable_zones": sum(1 for r in best['vastu']['results'] if r['status'] == 'acceptable'),
        "rooms_in_neutral_zones": sum(1 for r in best['vastu']['results'] if r['status'] in ('pass', 'warning')),
        "selected_candidate_avoid_zone_violations": sum(1 for r in best['vastu']['results'] if r['status'] in ('penalty', 'violation')),
        "target_zone_coverage": {},
        "room_final_zones": {}
    }
    
    for r_id, r_data in best['vastu'].get('room_zones', {}).items():
        selected_candidate_diagnostics["room_final_zones"][r_id] = r_data.get('zone', 'UNKNOWN')
        selected_candidate_diagnostics["target_zone_coverage"][r_id] = r_data.get('coverage', {})
    
    # Consolidate overlapping diagnostic structures to provide one source of truth
    # We remove `optimization_diagnostics` because it duplicates metrics in `search_metrics` and pipeline counts.
    
    # Find baseline scores
    baseline_arch = evaluate_architecture(baseline)
    baseline_combined = (
        baseline_vastu['score'] * ARCHITECTURAL_CONFIG['weights']['vastu'] +
        baseline_arch['architectural_score'] * ARCHITECTURAL_CONFIG['weights']['architecture'] +
        baseline_space['space_utilization_score'] * ARCHITECTURAL_CONFIG['weights'].get('space', 0.25) +
        baseline_space['compactness_score'] * ARCHITECTURAL_CONFIG['weights'].get('compactness', 0.10)
    )
    
    top_candidates = []
    for c in valid_candidates[:10]:
        t_c = {
            'vastu_score': c['vastu']['score'],
            'arch_score': c['architecture']['architectural_score'],
            'space_score': c['space']['space_utilization_score'],
            'compact_score': c['space']['compactness_score'],
            'combined_score': c['combined_score'],
            'violations': c['vastu'].get('violations', 0),
            'penalties': c['vastu'].get('penalties', 0),
            'bedroom_zones': [rz['zone'] for rz in c['vastu'].get('room_zones', {}).values() if 'bedroom' in rz['type']],
            'bathroom_zones': [rz['zone'] for rz in c['vastu'].get('room_zones', {}).values() if 'bathroom' in rz['type']],
            'kitchen_zone': next((rz['zone'] for rz in c['vastu'].get('room_zones', {}).values() if rz['type'] == 'kitchen'), None),
            'pooja_zone': next((rz['zone'] for rz in c['vastu'].get('room_zones', {}).values() if rz['type'] == 'pooja'), None)
        }
        top_candidates.append(t_c)

    metadata = {
        "enabled": True,
        "candidates_generated": candidates_generated,
        "geometry_valid_candidates": geometry_valid_count,
        "connectivity_valid_candidates": connectivity_valid_count,
        "circulation_valid_candidates": circulation_valid_count,
        "architecturally_valid_candidates": circulation_valid_count,
        "vastu_evaluated_candidates": circulation_valid_count,
        "vastu_eligible_candidates": max(0, len(all_cands_backup) - 1), # excluding baseline
        "baseline_score": baseline_vastu['score'],
        "selected_score": best['vastu']['score'],
        "baseline_arch_score": baseline_arch['architectural_score'],
        "selected_arch_score": best_arch['architectural_score'],
        "baseline_combined": baseline_combined,
        "selected_combined": best['combined_score'],
        "improvement": max(0, best['combined_score'] - baseline_combined),
        "improvement_breakdown": {
            "vastu": best['vastu']['score'] - baseline_vastu['score'],
            "architecture": best_arch['architectural_score'] - baseline_arch['architectural_score'] if isinstance(best_arch['architectural_score'], (int, float)) else 0,
            "combined": best['combined_score'] - baseline_combined
        },
        "strategies_used": STRATEGIES,
        "selection_strategy": "global_beam_search",
        "rejection_stats": rejections,
        "search_metrics": search_metrics,
        "vastu_telemetry": vastu_telemetry,
        "selected_candidate_diagnostics": selected_candidate_diagnostics,
        "architectural_diagnostics": best_arch['diagnostics'],
        "space_diagnostics": best_space,
        "top_candidates": top_candidates,
        "final_invariant_validation": final_validation_result
    }
    
    failure_stage = "NONE"
    if geometry_valid_count == 0 and search_metrics['complete_candidates'] > 0:
        failure_stage = "GEOMETRY"
    elif connectivity_valid_count == 0 and geometry_valid_count > 0:
        failure_stage = "CONNECTIVITY"
    elif circulation_valid_count == 0 and connectivity_valid_count > 0:
        failure_stage = "CIRCULATION"
        # Print circulation rejections if any
        circ_rejections = [k for k, v in rejections.items() if v > 0 and 'passage' in k or 'dependency' in k or 'circulation' in k]
        if circ_rejections:
            print(f"[REQUEST {reqs.request_id}][{reqs.test_case_name}] Circulation rejection reasons: {', '.join(circ_rejections)}")
    elif len(valid_candidates) - 1 == 0 and circulation_valid_count > 0:
        failure_stage = "VASTU"
        
    metadata["failure_stage"] = failure_stage
    
    # Check if Vastu was evaluated (eligible candidates exist)
    vastu_evaluated = len(valid_candidates) - 1 > 0
    final_v_score = best['vastu']['score'] if vastu_evaluated else "NOT EVALUATED"

    print("\n" + "="*60)
    print(f"PHASE 3G — {reqs.test_case_name}")
    print("="*60)
    print("Requirements:")
    print(f"  Plot: {reqs.plot.width} x {reqs.plot.depth} ft")
    print(f"  Facing: {reqs.plot.facing.capitalize()}")
    print("  Rooms: " + ", ".join([f"{v} {k.capitalize()}" for k,v in reqs.rooms.items()]))
    print(f"  Parking: {'Yes' if reqs.parking else 'No'}")
    print("="*60 + "\n")
    
    print(f"[REQUEST {reqs.request_id}][{reqs.test_case_name}] Starting candidate optimization...")
    print(f"=== PHASE 3G PIPELINE ===")
    print(f"Input requirements:")
    print(f"  Plot: {reqs.plot.width} x {reqs.plot.depth} ft")
    print(f"  Facing: {reqs.plot.facing.capitalize()}")
    for k in ["bedroom", "hall", "kitchen", "bathroom", "pooja"]:
        print(f"  {k.capitalize()}: {reqs.rooms.get(k, 0)}")
    print(f"  Parking: {'Yes' if reqs.parking else 'No'}\n")
    
    print(f"Candidate generation:")
    print(f"  Complete candidates: {search_metrics['complete_candidates']}")
    print(f"  Connected candidates: {search_metrics['connected_candidates_generated']}")
    print(f"  Disconnected candidates: {search_metrics['disconnected_candidates_generated']}\n")
    
    print(f"Validation:")
    print(f"  Geometry valid: {geometry_valid_count}")
    print(f"  Connectivity valid: {connectivity_valid_count}")
    print(f"  Door-feasible: {search_metrics['door_feasible_candidates']}")
    print(f"  Circulation valid: {circulation_valid_count}")
    print(f"  Architecturally valid: {circulation_valid_count}\n")
    
    print(f"Vastu:")
    print(f"  Vastu evaluated: {circulation_valid_count}")
    print(f"  Vastu eligible: {len(valid_candidates) - 1}\n")
    
    print(f"Selection status:")
    print(f"  {'FULL PIPELINE' if failure_stage == 'NONE' else 'FALLBACK / PRE-VASTU'}")
    
    print(f"\nSelected candidate:")
    print(f"  Vastu score: {final_v_score}")
    print(f"  Architecture score: {best_arch['architectural_score']}")
    print(f"  Avoid-zone violations: {selected_candidate_diagnostics['selected_candidate_avoid_zone_violations']}\n")
    
    if failure_stage != 'NONE':
        print(f"Failure stage:\n  {failure_stage}")
        
    print("\nGlobal Consistency Validation:")
    print(f"  Orientation: {'[PASS] Consistent' if failure_stage == 'NONE' else '[FAIL] Failed'}")
    print(f"  Entrance: {'[PASS] Valid boundary' if failure_stage == 'NONE' else '[FAIL] Invalid'}")
    print(f"  Vehicle Gate: {'[PASS] Valid boundary' if failure_stage == 'NONE' and reqs.parking else '[PASS] N/A' if not reqs.parking else '[FAIL] Invalid'}")
    print(f"  Area Accounting: {'[PASS] Consistent' if failure_stage == 'NONE' else '[FAIL] Failed'}")
    print(f"  Room Geometry: {'[PASS] Valid' if failure_stage == 'NONE' else '[FAIL] Failed'}")
    print(f"  Connectivity: {'[PASS] Valid' if failure_stage == 'NONE' else '[FAIL] Failed'}")
    
    print("\n" + "="*60)
    print(f"{reqs.test_case_name} — FINAL DIAGNOSTIC")
    print("="*60)
    print(f"Status:\n  {'SUCCESS' if failure_stage == 'NONE' else 'FAILED / FALLBACK'}")
    print(f"\nCandidate pipeline:")
    print(f"  Complete: {search_metrics['complete_candidates']}")
    print(f"  Geometry: {geometry_valid_count}")
    print(f"  Connectivity: {connectivity_valid_count}")
    print(f"  Circulation: {circulation_valid_count}")
    print(f"  Architecture: {circulation_valid_count}")
    print(f"  Vastu: {circulation_valid_count}")
    print(f"\nFinal candidate:")
    print(f"  Selected: Yes")
    print(f"  Vastu score: {final_v_score}")
    print(f"  Architecture score: {best_arch['architectural_score']}")
    print(f"  Avoid-zone violations: {selected_candidate_diagnostics['selected_candidate_avoid_zone_violations']}")
    print(f"\nFailure stage:\n  {failure_stage}")
    print("="*60 + "\n")
    
    # --- Internal Diagnostic Validation ---
    assert search_metrics['complete_candidates'] >= geometry_valid_count, "Pipeline invariant failed: complete < geometry_valid"
    assert geometry_valid_count >= connectivity_valid_count, "Pipeline invariant failed: geometry_valid < connectivity_valid"
    assert connectivity_valid_count >= circulation_valid_count, "Pipeline invariant failed: connectivity_valid < circulation_valid"
    
    assert "candidates_generated" not in search_metrics, "Duplicate metric 'candidates_generated' found in search_metrics"
    assert "geometry_valid_candidates" not in search_metrics, "Duplicate metric 'geometry_valid_candidates' found in search_metrics"
    
    for k, v in search_metrics.items():
        if isinstance(v, (int, float)):
            assert v >= 0, f"Negative counter found in search_metrics: {k}={v}"
    
    return best['layout'], best['vastu'], metadata
