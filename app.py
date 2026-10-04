import streamlit as st
import json
from dotenv import load_dotenv
import os

from llm.parser import parse_requirements
from layout.generator import generate_layout
from layout.validator import validate_layout
from renderer.svg_renderer import render_svg
from vastu import analyze_vastu

# Load environment variables
load_dotenv()

import datetime
import glob

HISTORY_DIR = "history"
if not os.path.exists(HISTORY_DIR):
    os.makedirs(HISTORY_DIR)

st.set_page_config(page_title="Indian AI Floor Plan Generator", layout="wide")

st.title("Indian AI Floor Plan Generator")
st.markdown("Phase 3G: Architectural Circulation & Vastu Optimization")

st.sidebar.markdown("### Status")
st.sidebar.markdown("🟢 Gemini API: Ready")

st.sidebar.markdown("### Settings")
enable_vastu = st.sidebar.checkbox("Enable Vastu Analysis", value=True)
enable_optimizer = st.sidebar.checkbox("Enable Vastu-Aware Layout Optimization", value=True)
agentic_mode = st.sidebar.checkbox("Enable Agentic Orchestration", value=False)

if 'reqs' not in st.session_state:
    st.session_state.reqs = None
if 'layout' not in st.session_state:
    st.session_state.layout = None
if 'validation_results' not in st.session_state:
    st.session_state.validation_results = None
if 'error_msg' not in st.session_state:
    st.session_state.error_msg = None
if 'warning_msg' not in st.session_state:
    st.session_state.warning_msg = None
if 'vastu_report' not in st.session_state:
    st.session_state.vastu_report = None
if 'opt_meta' not in st.session_state:
    st.session_state.opt_meta = None
if 'loaded_history_id' not in st.session_state:
    st.session_state.loaded_history_id = None
if 'infeasible_result' not in st.session_state:
    st.session_state.infeasible_result = None

st.sidebar.markdown("### Recent History")
history_files = sorted(glob.glob(os.path.join(HISTORY_DIR, "*.json")), reverse=True)
if not history_files:
    st.sidebar.write("No generations yet.")
else:
    for i, file_path in enumerate(history_files):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            st.sidebar.markdown(f"**{i+1}. {data.get('reqs_summary', 'Generation')}**")
            st.sidebar.write(f"- Score: {data.get('score', 0):.1f} / 100")
            st.sidebar.write(f"- Date: {os.path.basename(file_path).split('.')[0]}")
            
            if st.sidebar.button(f"Load #{i+1}", key=f"load_history_{i}"):
                with open(file_path, 'r', encoding='utf-8') as f:
                    full_data = json.load(f)
                    
                    # Ensure modules are imported
                    from models.requirements import FloorPlanRequirements
                    from models.floorplan import FloorPlan
                    
                    if 'reqs' in full_data and 'layout' in full_data:
                        st.session_state.reqs = FloorPlanRequirements(**full_data['reqs'])
                        st.session_state.layout = FloorPlan(**full_data['layout'])
                        st.session_state.validation_results = full_data.get('validation_results')
                        st.session_state.vastu_report = full_data.get('vastu_analysis')
                        st.session_state.opt_meta = full_data.get('optimization')
                        st.session_state.current_vastu_enabled = full_data.get('vastu_enabled', False)
                        st.session_state.current_opt_enabled = full_data.get('opt_enabled', False)
                    
                    st.session_state.raw_json_override = full_data
                    st.sidebar.success(f"Loaded full state for #{i+1}")
            st.sidebar.write("---")
        except Exception as e:
            st.sidebar.write(f"Error reading history file: {e}")

st.header("1. Natural Language Requirements")

test_cases = {
    "Test Case 1 - I have 30x40 land. I want 2 bedrooms, 1 hall, 1 kitchen, 2 bathrooms, 1 pooja room and parking. House should face west.": "I have 30x40 land. I want 2 bedrooms, 1 hall, 1 kitchen, 2 bathrooms, 1 pooja room and parking. House should face west.",
    "Test Case 2 - I have 40x50 land. I want 3 bedrooms, 1 hall, 1 kitchen, 2 bathrooms and parking. House should face east.": "I have 40x50 land. I want 3 bedrooms, 1 hall, 1 kitchen, 2 bathrooms and parking. House should face east.",
    "Test Case 3 - I have 30x50 land. I want 2 bedrooms, 1 hall, 2 kitchens, 1 bathroom, 1 pooja room and parking. House should face north.": "I have 30x50 land. I want 2 bedrooms, 1 hall, 2 kitchens, 1 bathroom, 1 pooja room and parking. House should face north.",
    "Test Case 4 - I have 30x40 land. I want 1 bedroom, 1 hall, 1 kitchen, 1 bathroom and parking. House should face west.": "I have 30x40 land. I want 1 bedroom, 1 hall, 1 kitchen, 1 bathroom and parking. House should face west."
}

if 'tc_selection' not in st.session_state:
    st.session_state.tc_selection = list(test_cases.keys())[0]
    st.session_state.text_area_widget = test_cases[list(test_cases.keys())[0]]

def on_tc_change():
    tc = st.session_state.tc_selection_widget
    st.session_state.tc_selection = tc
    st.session_state.text_area_widget = test_cases[tc]

st.selectbox("Select Test Case", list(test_cases.keys()), index=list(test_cases.keys()).index(st.session_state.tc_selection), key="tc_selection_widget", on_change=on_tc_change)

user_input = st.text_area("Describe your requirements:", height=100, key="text_area_widget")

if st.button("Generate Floor Plan", type="primary"):
    st.session_state.reqs = None
    st.session_state.layout = None
    st.session_state.validation_results = None
    st.session_state.error_msg = None
    st.session_state.warning_msg = None
    st.session_state.vastu_report = None
    st.session_state.opt_meta = None
    st.session_state.infeasible_result = None
    if 'raw_json_override' in st.session_state:
        del st.session_state['raw_json_override']
    st.session_state.current_vastu_enabled = enable_vastu
    st.session_state.current_opt_enabled = enable_optimizer
    
    if not os.getenv("GEMINI_API_KEY"):
        st.session_state.error_msg = "Error: GEMINI_API_KEY environment variable not set. Please create a .env file."
    else:
        if agentic_mode:
            with st.spinner("Running Multi-Agent Floor Plan Orchestrator..."):
                try:
                    from agents.orchestrator import FloorPlanOrchestrator
                    orchestrator = FloorPlanOrchestrator()
                    state = orchestrator.run(
                        user_prompt=user_input,
                        enable_vastu=enable_vastu,
                        enable_optimizer=enable_optimizer
                    )
                    st.session_state.agent_state = state
                    st.session_state.reqs = state.requirements
                    st.session_state.layout = state.selected_candidate
                    if state.validation_result:
                        st.session_state.validation_results = {
                            "valid": state.is_valid,
                            "errors": [i.message for i in state.active_issues if i.severity == "CRITICAL"],
                            "warnings": [i.message for i in state.active_issues if i.severity == "WARNING"],
                            "metrics": state.validation_result.metrics
                        }
                    if state.vastu_result and state.vastu_result.metrics.get("raw_report"):
                        st.session_state.vastu_report = state.vastu_result.metrics["raw_report"]
                    if state.optimization_result:
                        st.session_state.opt_meta = state.optimization_result.metrics
                    if not state.is_valid:
                        if state.orchestration_status == "INFEASIBLE_REQUEST" or state.status == "INFEASIBLE_REQUEST":
                            st.session_state.infeasible_result = state.get_infeasibility_summary()
                            st.session_state.error_msg = None
                        else:
                            st.session_state.infeasible_result = None
                            st.session_state.error_msg = state.error_message or "Agent orchestration could not produce a valid floor plan within retry budget."
                except Exception as e:
                    st.session_state.error_msg = str(e)
        else:
            with st.spinner("Extracting requirements using Gemini..."):
                try:
                    tc_name = st.session_state.get('tc_selection', "UNKNOWN TEST CASE").split(" — ")[0]
                    st.session_state.reqs = parse_requirements(user_input, test_case_name=tc_name)
                    
                    reqs = st.session_state.reqs
                    stated_area = reqs.plot.area
                    calc_area = reqs.plot.width * reqs.plot.depth
                    if stated_area and abs(stated_area - calc_area) > 1:
                        st.session_state.warning_msg = f"Inconsistency detected: {reqs.plot.width} × {reqs.plot.depth} {reqs.plot.unit} corresponds to {calc_area} sq.{reqs.plot.unit}, while the stated area is {stated_area} sq.{reqs.plot.unit}. Using derived dimensions."
                        
                    for attempt in range(3):
                        st.session_state.layout = generate_layout(reqs)
                        st.session_state.validation_results = validate_layout(st.session_state.layout)
                        
                        if st.session_state.current_vastu_enabled:
                            # Always analyze baseline for reference
                            st.session_state.vastu_report = analyze_vastu(st.session_state.layout)
                            
                            if st.session_state.current_opt_enabled:
                                try:
                                    from layout.vastu_optimizer import optimize_layout
                                    best_layout, best_vastu, opt_meta = optimize_layout(reqs, st.session_state.layout, st.session_state.vastu_report)
                                    
                                    print("Finished optimize_layout")
                                    # Final independent validation pass from actual geometry
                                    final_validation = validate_layout(best_layout)
                                    print("Finished validate_layout")
                                    final_vastu = analyze_vastu(best_layout)
                                    print("Finished analyze_vastu")
                                    
                                    st.session_state.layout = best_layout
                                    st.session_state.vastu_report = final_vastu
                                    st.session_state.opt_meta = opt_meta
                                    st.session_state.validation_results = final_validation
                                    
                                    if opt_meta.get('failure') is None:
                                        break
                                    else:
                                        print(f"Attempt {attempt + 1} failed with stage {opt_meta.get('failure')}. Retrying...")
                                except Exception as e:
                                    # Fallback to baseline gracefully
                                    st.session_state.opt_meta = {
                                        "enabled": True,
                                        "candidates_generated": 0,
                                        "baseline_score": st.session_state.vastu_report['score'],
                                        "selected_score": st.session_state.vastu_report['score'],
                                        "improvement": 0,
                                        "error": str(e)
                                    }
                            else:
                                break
                        else:
                            break
                
                    # Save to history
                    if st.session_state.validation_results and st.session_state.validation_results['valid']:
                        rooms_str = ", ".join(f"{count} {room}" for room, count in reqs.rooms.items())
                        score = st.session_state.vastu_report['score'] if st.session_state.vastu_report else 0
                        if st.session_state.opt_meta and 'selected_combined' in st.session_state.opt_meta:
                            score = st.session_state.opt_meta['selected_combined']
                        
                        history_item = {
                            "reqs_summary": f"{reqs.plot.width}x{reqs.plot.depth} {reqs.plot.facing.capitalize()} Facing",
                            "rooms": rooms_str,
                            "score": score,
                            "vastu_enabled": st.session_state.current_vastu_enabled,
                            "opt_enabled": st.session_state.current_opt_enabled,
                            "reqs": reqs.model_dump(),
                            "layout": st.session_state.layout.model_dump(),
                            "validation_results": st.session_state.validation_results
                        }
                        
                        if st.session_state.vastu_report:
                            history_item['vastu_analysis'] = st.session_state.vastu_report
                        if enable_optimizer and st.session_state.opt_meta:
                            history_item['optimization'] = st.session_state.opt_meta
                            arch_diag = st.session_state.opt_meta.get('architectural_diagnostics', {})
                            history_item['room_realism'] = {
                                "score": arch_diag.get('room_realism_score', 100),
                                "rejections": arch_diag.get('room_realism_rejections', 0),
                                "rooms": arch_diag.get('room_realism_details', {})
                            }
                            history_item['architectural_diagnostics'] = arch_diag
                            
                        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                        file_name = os.path.join(HISTORY_DIR, f"{timestamp}.json")
                        with open(file_name, 'w', encoding='utf-8') as f:
                            json.dump(history_item, f, indent=4)
                            
                        # Prune history to 5 items
                        existing_files = sorted(glob.glob(os.path.join(HISTORY_DIR, "*.json")))
                        while len(existing_files) > 5:
                            os.remove(existing_files.pop(0))
                except Exception as e:
                    st.session_state.error_msg = str(e)

if st.session_state.get('infeasible_result'):
    inf = st.session_state.infeasible_result
    st.warning("### ⚠️ No valid floor plan found under the current constraints")
    st.markdown(
        "The requested combination of plot dimensions, rooms, parking and circulation constraints "
        "could not be satisfied under the current system constraints."
    )
    st.markdown(f"**Primary issue:** {inf.get('reason') or inf.get('dominant_issue')}")
    if inf.get('affected_rooms'):
        st.markdown(f"**Affected rooms:** {', '.join(inf['affected_rooms'])}")
    st.markdown("**Suggested changes:**")
    for change in inf.get('recommended_relaxations', [
        "Increase plot size",
        "Reduce number of rooms",
        "Modify parking requirement",
        "Relax applicable architectural constraints"
    ]):
        st.markdown(f"• {change}")
    st.info("ℹ️ No invalid floor plan was rendered.")
elif st.session_state.error_msg:
    st.error(st.session_state.error_msg)
    
if st.session_state.warning_msg:
    st.warning(st.session_state.warning_msg)

if st.session_state.reqs:
    reqs = st.session_state.reqs
    st.header("2. Extracted Requirements")
    col1, col2 = st.columns(2)
    with col1:
        st.write(f"**Plot Dimensions:** {reqs.plot.width} x {reqs.plot.depth} {reqs.plot.unit}")
        st.write(f"**Facing:** {reqs.plot.facing.capitalize()}")
        st.write(f"**Parking Required:** {'Yes' if reqs.parking else 'No'}")
    with col2:
        st.write("**Rooms:**")
        for room, count in reqs.rooms.items():
            st.write(f"- {room.capitalize()}: {count}")

    if st.session_state.get('agent_state'):
        ag_state = st.session_state.agent_state
        with st.expander("🤖 Multi-Agent Execution Trace & Deterministic Diagnosis", expanded=True):
            st.markdown(f"**Orchestration Status:** `{ag_state.status}` | **Iterations:** `{ag_state.iteration + 1}/{ag_state.max_iterations}`")
            for step in ag_state.trace:
                badge = "🟢" if step.status == "SUCCESS" else ("🟡" if step.status == "WARNING" else "🔴")
                st.markdown(f"{badge} **{step.agent_name}** (`{step.status}`): {step.message} *({step.duration_ms:.1f}ms)*")
            if ag_state.action_history:
                st.markdown("**Deterministic Diagnosis & Action Log:**")
                for act in ag_state.action_history:
                    st.write(f"- `{act.action_type}` on target `{act.target}`: {act.reason}")
            if ag_state.structural_evidence:
                st.markdown("**Structural Evidence:**")
                st.json(ag_state.structural_evidence)

    st.header("3. Floor Plan Analysis")
    val = st.session_state.validation_results
    plan = st.session_state.layout
    
    if plan and val:
        col3, col4 = st.columns(2)
        with col3:
            st.write(f"**Plot Area:** {plan.plot_area} sq.ft")
            room_area_sum = sum(r.area for r in plan.rooms if r.type != 'parking')
            st.write(f"**Room Area Sum:** {room_area_sum} sq.ft")
            st.write(f"**Building Footprint Area:** {plan.built_area} sq.ft")
            st.write(f"**Space Utilization:** {plan.utilization_percentage:.1f}%")
            
            req_room_count = sum(reqs.rooms.values())
            gen_room_count = len([r for r in plan.rooms if r.type != 'parking'])
            st.write(f"**Habitable Rooms:** {gen_room_count} / {req_room_count}")
            st.write(f"**Parking Spaces:** {1 if reqs.parking else 0}")
            
        with col4:
            st.write(f"**Entrance Direction:** {plan.facing.capitalize()}")
            if val["valid"] and gen_room_count == req_room_count:
                st.write("✓ Geometry valid")
                st.write("✓ All rooms connected")
                st.write("✓ Main entrance connected")
                st.write("✓ No room overlaps")
                st.write("✓ All rooms inside plot")
                st.write("✓ All requested rooms placed")
            else:
                if not val["valid"]:
                    st.write("❌ Geometry invalid")
                if gen_room_count != req_room_count:
                    st.write("❌ Missing requested rooms")
    
    if val and val["valid"] and gen_room_count == req_room_count:
        st.success("Layout passed heuristic geometry validation and all rooms were placed.")
        if val["warnings"]:
            for w in val["warnings"]:
                st.warning(w)
    elif val and val["valid"]:
        st.warning(f"Layout is geometrically valid, but only {gen_room_count} out of {req_room_count} rooms could fit on the plot.")
    elif val and not st.session_state.get('infeasible_result'):
        st.error("Layout failed geometry validation. The generated plan is invalid.")
        for e in val["errors"]:
            st.error(e)
            
    st.header("4. Generated Floor Plan")
    if val and val["valid"]:
        
        show_vastu_grid = False
        if enable_vastu and st.session_state.vastu_report:
            show_vastu_grid = st.checkbox("Show Vastu Grid Overlay", value=False)
            
        print("Rendering SVG...")
        svg = render_svg(plan.plot_width, plan.plot_depth, plan.facing, plan, show_vastu_grid=show_vastu_grid, vastu_data=st.session_state.vastu_report)
        st.markdown(svg, unsafe_allow_html=True)
        
        st.markdown("### Connections:")
        if plan.entrance:
            st.write(f"- Exterior → Main Entrance → {plan.entrance.room.capitalize().replace('_', ' ')}")
            
        if hasattr(plan, 'vehicle_gate') and plan.vehicle_gate:
            st.write(f"- Exterior → Vehicle Gate → {plan.vehicle_gate.room.capitalize().replace('_', ' ')}")
            
        for door in plan.doors:
            if not door.from_room.startswith('parking') and not door.to_room.startswith('parking'):
                st.write(f"- {door.from_room.capitalize().replace('_', ' ')} → {door.to_room.capitalize().replace('_', ' ')}")
            
    else:
        st.info("Floor plan will not be displayed due to validation errors.")
        
    if enable_vastu and st.session_state.vastu_report:
        st.header("5. Vastu Analysis")
        
        if enable_optimizer and st.session_state.opt_meta:
            om = st.session_state.opt_meta
            st.markdown("### Global Search")
            st.write(f"**Candidates Generated:** {om.get('candidates_generated', 0)}")
            st.write(f"**Geometry Valid Candidates:** {om.get('geometry_valid_candidates', 0)}")
            st.write(f"**Connectivity Valid Candidates:** {om.get('connectivity_valid_candidates', 0)}")
            st.write(f"**Circulation Valid Candidates:** {om.get('circulation_valid_candidates', 0)}")
            st.write(f"**Architecturally Valid Candidates:** {om.get('architecturally_valid_candidates', 0)}")
            st.write(f"**Vastu Eligible Candidates:** {om.get('vastu_eligible_candidates', 0)}")
            
            with st.expander("View Rejection Stats"):
                st.markdown("### Circulation Rejection Stats")
                stats = om.get('rejection_stats', {})
                st.write(f"Bathroom passage rejections: {stats.get('bathroom_passage_rejections', 0)}")
                st.write(f"Kitchen passage rejections: {stats.get('kitchen_passage_rejections', 0)}")
                st.write(f"Bedroom access rejections: {stats.get('bedroom_access_rejections', 0)}")
                st.write(f"Passage dependency rejections: {stats.get('passage_dependency_rejections', 0)}")
                st.markdown("### All Rejection Stats")
                st.json(stats)
                
            with st.expander("View Search Metrics"):
                st.markdown("### Global Search Metrics")
                st.json(om.get('search_metrics', {}))
                
                if 'room_candidate_diagnostics' in om.get('search_metrics', {}):
                    st.markdown("### Room Candidate Diagnostics")
                    st.json(om['search_metrics']['room_candidate_diagnostics'])
                    
            if 'vastu_telemetry' in om:
                with st.expander("View Vastu Telemetry"):
                    st.markdown("### Vastu Telemetry")
                    st.json(om['vastu_telemetry'])
                    
            st.markdown("### Selection Objective")
            st.write("The selected layout optimally balances: **Vastu**, **architectural quality**, **space efficiency**, **compactness**, **circulation**, and **room realism**.")
            st.write(f"- Vastu Weight: {om.get('weights', {}).get('vastu', 0.20)}")
            st.write(f"- Architecture Weight: {om.get('weights', {}).get('architecture', 0.45)}")
            st.write(f"- Space Efficiency Weight: {om.get('weights', {}).get('space', 0.25)}")
            st.write(f"- Compactness Weight: {om.get('weights', {}).get('compactness', 0.10)}")
            
            st.markdown("### Optimization Result")
            eligible = om.get('vastu_eligible_candidates', 0)
            if eligible <= 0:
                st.write("**No Vastu-eligible candidate found** (All generated candidates failed circulation or hard constraints).")
                st.write(f"**Baseline Vastu Score:** {om.get('baseline_score', 0)} / 100")
            else:
                st.write(f"**Baseline Vastu Score:** {om.get('baseline_score', 0)} / 100")
                st.write(f"**Optimized Vastu Score:** {om.get('selected_score', 0)} / 100")
            st.write("")
            b_arch = om.get('baseline_arch_score', 0)
            o_arch = om.get('selected_arch_score', 0)
            b_comb = om.get('baseline_combined', 0)
            o_comb = om.get('selected_combined', 0)
            st.write(f"**Baseline Architectural Score:** {b_arch:.1f} / 100" if isinstance(b_arch, (int, float)) else f"**Baseline Architectural Score:** {b_arch}")
            st.write(f"**Optimized Architectural Score:** {o_arch:.1f} / 100" if isinstance(o_arch, (int, float)) else f"**Optimized Architectural Score:** {o_arch}")
            st.write("")
            st.write(f"**Baseline Combined Score:** {b_comb:.1f} / 100" if isinstance(b_comb, (int, float)) else f"**Baseline Combined Score:** {b_comb}")
            st.write(f"**Optimized Combined Score:** {o_comb:.1f} / 100" if isinstance(o_comb, (int, float)) else f"**Optimized Combined Score:** {o_comb}")
            
            st.markdown("### Why This Layout Was Selected")
            arch_diag = om.get('architectural_diagnostics', {})
            fv = om.get('final_invariant_validation', {})
            st.write(f"- **Geometry**: {'Valid' if fv.get('geometry', True) else 'Invalid'}")
            st.write(f"- **Connectivity**: {'Valid' if fv.get('connectivity', True) else 'Invalid'}")
            st.write(f"- **Circulation**: {'Valid' if fv.get('circulation', True) else 'Invalid'}")
            st.write(f"- **Room Realism**: {'Valid' if arch_diag.get('room_realism_rejections', 0) == 0 else 'Warnings/Violations'}")
            st.write(f"- **Vastu**: {om.get('selected_score', 0)} / 100")
            st.write(f"- **Architectural Quality**: {o_arch:.1f}" if isinstance(o_arch, (int, float)) else f"- **Architectural Quality**: {o_arch}")
            st.write(f"- **Combined Score**: {o_comb:.1f}" if isinstance(o_comb, (int, float)) else f"- **Combined Score**: {o_comb}")
            st.write("\n*Candidate was selected because it provided the strongest overall balance between architectural realism, circulation, space efficiency, compactness, and configured Vastu preferences.*")
            
            st.markdown("#### Improvement:")
            imp = om.get('improvement_breakdown', {})
            imp_arch = imp.get('architecture', 0)
            imp_comb = imp.get('combined', 0)
            st.write(f"- Vastu: +{imp.get('vastu', 0)}")
            st.write(f"- Architecture: +{imp_arch:.1f}" if isinstance(imp_arch, (int, float)) else f"- Architecture: +{imp_arch}")
            st.write(f"- Combined: +{imp_comb:.1f}" if isinstance(imp_comb, (int, float)) else f"- Combined: +{imp_comb}")
            
            st.markdown("### Architectural Analysis")
            arch_diag = om.get('architectural_diagnostics', {})
            st.write(f"**Architectural Score:** {o_arch:.1f} / 100" if isinstance(o_arch, (int, float)) else f"**Architectural Score:** {o_arch}")
            st.write(f"**Circulation Score:** {arch_diag.get('circulation_score', 0):.1f} / 100" if isinstance(arch_diag.get('circulation_score', 0), (int, float)) else f"**Circulation Score:** {arch_diag.get('circulation_score', 0)}")
            st.write(f"**Direct Access:** {arch_diag.get('direct_access_score', 0):.1f} / 100")
            st.write(f"**Functional Adjacency:** {arch_diag.get('functional_adjacency_score', 0):.1f} / 100")
            st.write(f"**Privacy:** {arch_diag.get('privacy_score', 0):.1f} / 100")
            st.write(f"**Door Accessibility:** {arch_diag.get('door_access_score', 0):.1f} / 100")
            st.write(f"**Room Realism Score:** {arch_diag.get('room_realism_score', 0):.1f} / 100")
            
            st.markdown("### Room Realism Analysis")
            details = arch_diag.get('room_realism_details', {})
            if details:
                st.markdown("| Room | Size (W × D) | Area | Aspect Ratio | Status |")
                st.markdown("| --- | --- | --- | --- | --- |")
                for r_id, d in details.items():
                    name = r_id.replace('_', ' ').capitalize()
                    status = "✓ Valid" if d['status'] == 'valid' else ("⚠ Warning" if d['status'] == 'warning' else "❌ Violation")
                    st.markdown(f"| {name} | {d['width']:.1f} × {d['depth']:.1f} ft | {d['area']:.1f} sq.ft | {d['aspect_ratio']:.2f} | {status} |")
            else:
                st.write("No room realism details available.")
            
            passages = arch_diag.get('passage_rooms', [])
            if not passages:
                st.write("**Passage Rooms:** None")
            else:
                st.write("**Passage Rooms:**")
                for pr in passages:
                    st.write(f"- {pr.capitalize().replace('_', ' ')}")
                    
            dependencies = arch_diag.get('passage_dependencies', [])
            if dependencies:
                with st.expander("Passage Dependencies"):
                    for dep in dependencies:
                        st.write(f"- **{dep['passage_room'].capitalize().replace('_', ' ')}**: {dep['reason']}")
                        
            st.write(f"**Hall Direct Connections:** {arch_diag.get('hall_direct_access_count', 0)}")
            st.write(f"**Indirect Access Count:** {arch_diag.get('indirect_access_count', 0)}")
            st.write(f"**Average Room Path:** {arch_diag.get('average_path_length', 0)}")
            st.write(f"**Maximum Room Path:** {arch_diag.get('max_path_length', 0)}")
            
            st.markdown("### Hard Validation")
            final_val = om.get('final_invariant_validation', {})
            
            st.write(f"{'✓' if final_val.get('geometry') else '✗'} Geometry valid")
            st.write(f"{'✓' if final_val.get('connectivity') else '✗'} Connectivity valid")
            st.write(f"{'✓' if final_val.get('circulation') else '✗'} Circulation valid")
            if not final_val.get('circulation') and final_val.get('hard_violations'):
                for hv in final_val['hard_violations']:
                    if hv.get('type') == 'unreachable_room':
                        st.write(f"  - **Reason**: Room {hv.get('room', 'unknown')} is disconnected and unreachable from the hall.")
                    else:
                        st.write(f"  - **Reason**: {hv.get('passage_room', 'Room')} is used as a passage to {', '.join(hv.get('dependent_rooms', []))}")
                    
            st.write(f"{'✓' if final_val.get('architecture') else '✗'} Architectural constraints valid")
            
            met_valid = final_val.get('metrics', True)
            st.write(f"{'✓' if met_valid else '✗'} Metric invariants valid")
            
            st.write(f"{'✓' if final_val.get('valid') else '✗'} Final candidate valid")
            
            diag = om.get('selected_candidate_diagnostics', {})
            for r_id, final_zone in diag.get('room_final_zones', {}).items():
                # Find status from vastu report
                for res in st.session_state.vastu_report['results']:
                    if res['room'] == r_id and res['status'] == 'preferred':
                        st.write(f"✓ {res['room_name'].capitalize()} is in the preferred {final_zone} zone")
                    
            if 'selected_candidate_diagnostics' in om:
                st.markdown("### Room Placement Summary")
                diag = om['selected_candidate_diagnostics']
                st.write(f"**Preferred-zone matches:** {diag.get('rooms_in_preferred_zones', 0)}")
                st.write(f"**Acceptable-zone matches:** {diag.get('rooms_in_acceptable_zones', 0)}")
                st.write(f"**Selected-Candidate Avoid-zone violations:** {diag.get('selected_candidate_avoid_zone_violations', 0)}")
                
                final_zones = diag.get('room_final_zones', {})
                for res in st.session_state.vastu_report['results']:
                    st.write(f"- {res['room_name'].capitalize()} → {final_zones.get(res['room'], 'UNKNOWN')} ({res['status'].capitalize()})")
                    
            if 'space_diagnostics' in om:
                st.markdown("### Building Diagnostics")
                s_diag = om['space_diagnostics']
                
                met_inv = s_diag.get('metric_invariants', {})
                if met_inv.get('valid', True):
                    st.write("✓ **Geometrically consistent**")
                else:
                    st.write("✗ **Metric inconsistency detected**")
                    for failure in met_inv.get('failures', []):
                        st.write(f"  - Failed rule: `{failure['rule']}`")
                
                st.write(f"**Building Components:** {s_diag.get('building_components', 1)}")
                st.write(f"**Habitable Footprint Area:** {s_diag.get('habitable_room_area', s_diag.get('building_footprint_area', 0)):.1f} sq.ft")
                st.write(f"**Parking Area:** {s_diag.get('parking_area', 0):.1f} sq.ft")
                st.write(f"**Total Occupied Area:** {s_diag.get('total_occupied_area', 0):.1f} sq.ft")
                st.write(f"**Building Envelope Area:** {s_diag.get('building_envelope_area', 0):.1f} sq.ft")
                st.write(f"**Building BBox Area:** {s_diag.get('building_bbox_area', 0):.1f} sq.ft")
                st.write(f"**Internal Void Area:** {s_diag.get('internal_void_area', 0):.1f} sq.ft")
                st.write(f"**Unallocated Buildable Area:** {s_diag.get('unallocated_buildable_area', 0):.1f} sq.ft")
                st.write(f"**Largest Unused Region:** {s_diag.get('largest_unused_region', 0):.1f} sq.ft")
                st.write(f"**Unused Region Count:** {s_diag.get('unused_region_count', 0)}")
                st.write(f"**Compactness:** {s_diag.get('compactness', 0):.1f}%")
            
            if om.get('improvement', 0) <= 0:
                st.info("Baseline layout retained because no candidate produced a better valid Vastu score.")
        
        vr = st.session_state.vastu_report
        
        st.markdown(f"**Configured Vastu Preference Score:** {vr['score']} / 100")
        st.caption("Score represents satisfaction of the Vastu rules configured in this project. It is not a scientific or universal measure of architectural quality.")
        st.markdown(f"**Rules:** {vr['passed']} Passed | {vr['warnings']} Warnings | {vr['violations']} Hard Violations")
        
        st.markdown("### Rule Results")
        for res in vr['results']:
            zone = res['zone']
            p_zones = res.get('preferred_zones', [])
            a_zones = res.get('acceptable_zones', [])
            av_zones = res.get('avoid_zones', [])
            
            st.markdown(f"#### {res['room_name']}")
            st.write(f"**Dominant Zone:** {zone}")
            
            # Show coverage
            r_zones = st.session_state.vastu_report.get('room_zones', {}).get(res['room'])
            if r_zones:
                st.write(f"**Preferred Coverage:** {r_zones.get('preferred_zone_coverage', 0)*100:.1f}%")
                st.write(f"**Acceptable Coverage:** {r_zones.get('acceptable_zone_coverage', 0)*100:.1f}%")
                st.write(f"**Neutral Coverage:** {r_zones.get('neutral_zone_coverage', 0)*100:.1f}%")
                st.write(f"**Avoid Coverage:** {r_zones.get('avoid_zone_coverage', 0)*100:.1f}%")
            
            if p_zones:
                st.write(f"**Preferred:** {', '.join(p_zones)}")
            if a_zones:
                st.write(f"**Acceptable:** {', '.join(a_zones)}")
            if av_zones:
                st.write(f"**Avoid:** {', '.join(av_zones)}")
                
            if res['status'] == 'preferred':
                st.success(f"✓ Pass: {res['message']}")
            elif res['status'] == 'pass':
                st.success(f"✓ Pass: {res['message']}")
            elif res['status'] == 'acceptable':
                st.success(f"✓ Acceptable: {res['message']}")
            elif res['status'] == 'warning':
                st.warning(f"⚠ Warning: {res['message']}")
            else:
                st.error(f"❌ Violation: {res['message']}")
                

if st.session_state.reqs or 'raw_json_override' in st.session_state:
    st.header("6. Raw JSON")
    with st.expander("Show raw requirements JSON"):
        if 'raw_json_override' in st.session_state:
            out_json = st.session_state.raw_json_override
        else:
            out_json = reqs.model_dump()
            if st.session_state.get('current_vastu_enabled', False):
                out_json['vastu_enabled'] = True
                if st.session_state.vastu_report:
                    out_json['vastu_analysis'] = st.session_state.vastu_report
                if st.session_state.get('current_opt_enabled', False) and st.session_state.opt_meta:
                    out_json['optimization'] = st.session_state.opt_meta
                    arch_diag = st.session_state.opt_meta.get('architectural_diagnostics', {})
                    space_diag = st.session_state.opt_meta.get('space_diagnostics', {})
                    
                    out_json['building_diagnostics'] = {
                        "building_component_count": space_diag.get('building_components', 1),
                        "building_footprint_area": space_diag.get('building_footprint_area', 0),
                        "building_envelope_area": space_diag.get('building_envelope_area', 0),
                        "building_bbox_area": space_diag.get('building_bbox_area', 0),
                        "internal_void_area": space_diag.get('internal_void_area', 0),
                        "total_occupied_area": space_diag.get('total_occupied_area', 0),
                        "unallocated_buildable_area": space_diag.get('unallocated_buildable_area', 0),
                        "largest_unused_region": space_diag.get('largest_unused_region', 0),
                        "unused_region_count": space_diag.get('unused_region_count', 0),
                        "plot_coverage": space_diag.get('plot_coverage', 0),
                        "room_coverage": space_diag.get('room_coverage', 0),
                        "space_utilization": space_diag.get('space_utilization', 0),
                        "compactness": space_diag.get('compactness', 0)
                    }
                    
                    out_json['circulation_diagnostics'] = {
                        "entrance_access_score": arch_diag.get('direct_access_score', 100),
                        "parking_access_score": arch_diag.get('door_access_score', 100),
                        "average_path_length": arch_diag.get('average_path_length', 0),
                        "maximum_path_length": arch_diag.get('max_path_length', 0),
                        "passage_room_count": len(arch_diag.get('passage_rooms', [])),
                        "isolated_room_count": arch_diag.get('indirect_access_count', 0)
                    }
                    
                    out_json['room_realism'] = {
                        "score": arch_diag.get('room_realism_score', 100),
                        "rejections": arch_diag.get('room_realism_rejections', 0),
                        "rooms": arch_diag.get('room_realism_details', {})
                    }
                    out_json['architectural_diagnostics'] = arch_diag
            else:
                out_json['vastu_enabled'] = False
            
        st.json(out_json)

if st.button("Clear Results"):
    keys_to_clear = ['reqs', 'layout', 'validation_results', 'error_msg', 'warning_msg', 'vastu_report', 'opt_meta', 'raw_json_override', 'current_vastu_enabled', 'current_opt_enabled']
    for k in keys_to_clear:
        if k in st.session_state:
            del st.session_state[k]
    st.rerun()
