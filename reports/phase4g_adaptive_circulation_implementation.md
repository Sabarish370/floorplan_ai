# PHASE 4G — ADAPTIVE CIRCULATION TOPOLOGY IMPLEMENTATION REPORT

## 1. Objective
The primary objective of Phase 4G was to implement an **Adaptive Circulation Topology** within the Indian AI Floor Plan Generator. The current production system utilizes a Hall-centered star topology where all primary rooms directly attach to the central Hall. Phase 4F demonstrated that on narrow, constrained plots (specifically the benchmark 25×40 ft South-facing plot with 2 bedrooms, 1 hall, 1 kitchen, 2 bathrooms, 1 pooja, and parking), the star topology fails due to Hall frontage exhaustion. Phase 4G implements an internal circulation node as an **adaptive fallback** to bridge this bottleneck without degrading architectural quality, privacy invariants, door feasibility, or Vastu scoring.

---

## 2. Current Star Topology Limitation
In the standard Hall-centered star topology:
```
           EXTERIOR
              |
        MAIN ENTRANCE
              |
             HALL
        /   /  |  \   \
      BED BED KIT BATH POOJA
```
For the 25×40 ft South-facing plot:
- Plot width is 25 ft and depth is 40 ft (1000 sq.ft total area).
- Required parking (10×16–18 ft) consumes 10 ft of the 25 ft South frontage, leaving at most 15 ft for the Hall South boundary.
- The Hall interior North wall available for room connections is only 14–15 ft wide.
- Direct attachment of 2 bedrooms (minimum 10 ft frontage each) and 1 kitchen (minimum 10 ft frontage) demands at least 30 ft of perimeter, creating a severe 15 ft frontage deficit.
- Consequently, beam search under the strict star topology produced 0 valid complete candidates on 25×40 South.

---

## 3. Why Adaptive Circulation was Required
Adaptive circulation introduces an intermediate common circulation spine:
```
           EXTERIOR
              |
        MAIN ENTRANCE
              |
             HALL
              |
         CIRCULATION
         /    |    \
      BED1   BED2  KITCHEN
        |      |      |
      BATH1  BATH2  POOJA
```
- By adding a 4×10 ft (40 sq.ft) circulation spine attached to the Hall's North interior edge:
  - Hall direct boundary demand drops from 30 ft down to 14 ft (accommodating `circulation_1` and `bedroom_2` or `kitchen_1`).
  - `circulation_1` distributes traffic to `bedroom_1` and `kitchen_1` without using any private bedroom or kitchen as a passage.
  - The bathrooms attach to bedrooms as en-suite facilities, and Pooja connects to Kitchen.
  - All 9 requested spaces are placed with 100% geometric and architectural validity.

Crucially, circulation is **adaptive**: it is only engaged when the preferred direct Hall-access star topology cannot satisfy layout constraints.

---

## 4. Files Modified
1. `layout/generator.py`:
   - Added `generate_circulation_candidates` to deterministically calculate circulation candidate geometry (width, depth, location) based on plot dimensions, facing, parking location, and Hall interior edge.
   - Updated `generate_room_candidates` to allow `circulation` as an allowed parent node for bedrooms, kitchens, bathrooms, and pooja.
   - Configured fallback execution in `generate_layout_beam_search` so that Star Topology (Root A and Root B) is always evaluated first; only if Star Topology produces 0 valid plans is the adaptive circulation spine evaluated.
   - Ensured `generate_layout` falls back to beam search if heuristic doors are incomplete.
2. `config/architecture_rules.py`:
   - Added `"circulation": {"can_be_passage": True}` to `PASSAGE_POLICY`.
   - Added `"circulation": 0` to `PASSAGE_ROOM_PENALTIES`.
3. `layout/architecture.py`:
   - Updated `validate_circulation_constraints` to recognize intermediate paths through `circulation` as valid common circulation, avoiding false `DIRECT_ACCESS_VIOLATION` rejections.
   - Updated `evaluate_architecture` to exclude internal circulation from residential room realism scale bounds while verifying its geometric soundness.
4. `layout/expansion.py`:
   - Excluded `circulation` from post-placement room expansion to prevent expanding circulation into adjacent rooms.
5. `layout/footprint_optimizer.py`:
   - Excluded `circulation` from footprint void expansion so circulation dimensions remain strictly bounded.
6. `layout/vastu_optimizer.py`:
   - Excluded `circulation` from user-requested room count validation checks (`gen_count`).
7. `renderer/svg_renderer.py`:
   - Added visual styling for circulation regions (`"circulation": "#f0f4c3"`).
8. `tests/test_regression_agentic.py`:
   - Updated 25×40 South regression to verify VALID status and presence of circulation under Phase 4G, and added dedicated test for genuinely infeasible plot geometry (`test_regression_structural_infeasibility`).
9. `tests/test_phase4g_circulation.py`:
   - Created comprehensive test suite verifying all 10 Phase 4G acceptance requirements.

---

## 5. Circulation Data Model
Circulation is formalized as an internal geometric entity conforming to the standard `Room` schema:
```json
{
    "id": "circulation_1",
    "type": "circulation",
    "name": "Circulation",
    "x": 10.0,
    "y": 14.0,
    "width": 4.0,
    "depth": 10.0,
    "area": 40.0
}
```
Key semantics:
- Internal layout entity: not counted as a requested bedroom, hall, kitchen, bathroom, or pooja.
- Real physical geometry: rendered in SVG, included in footprint/coverage accounting, and participates in door and collision graphs.
- Passage node: designated with `can_be_passage: True` in `PASSAGE_POLICY`.

---

## 6. Topology-Selection Logic
The topology decision follows a strict fallback priority:
```
1. Generate Root A (Star Topology)
      ↓
2. Beam search on Root A
      ↓
3. Validate geometry + doors + privacy
      ↓
   [Valid plans exist?] ──YES──> Accept Star Topology (Root A)
      ↓ NO
4. Generate Root B (Star Topology)
      ↓
5. Beam search on Root B
      ↓
6. Validate geometry + doors + privacy
      ↓
   [Valid plans exist?] ──YES──> Accept Star Topology (Root B)
      ↓ NO
7. Evaluate Adaptive Circulation Topology
      ↓
8. Generate circulation candidate(s) attached to Hall interior edge
      ↓
9. Re-run room placement on Circulation Root(s)
      ↓
10. Validate geometry + doors + privacy + connectivity
      ↓
   [Valid plans exist?] ──YES──> Accept Circulation Topology (CIRCULATION_SPINE)
      ↓ NO
11. Return [] / Classify as INFEASIBLE_REQUEST
```

---

## 7. Circulation Dimension-Generation Logic
Circulation dimensions are derived deterministically by `generate_circulation_candidates(initial_rooms, reqs, plot_w, plot_d, facing)`:
- Width: derived from minimum standard hallway width (`circ_w = 4.0 ft`), which comfortably accommodates 3.0 ft internal doors and clearance.
- Depth: derived from branch span needed to bridge front-to-back rooms (`circ_d = 10.0 ft` on plots $\le 1200$ sq.ft; scaled up to 12.0 ft on deeper plots).
- Placement: attached directly to the Hall's interior edge opposite the road (e.g. at $y = \text{hall.y} - \text{circ\_d}$ for South-facing plots).
- Rejections: candidates outside plot boundaries, overlapping parking/Hall, or providing $< 3.0$ ft shared edge with Hall are rejected immediately.

---

## 8. Door Graph Integration
Circulation is a full participant in `generate_internal_doors`:
- Door 1: `hall_1` $\leftrightarrow$ `bedroom_2` (width: 3.0 ft, horizontal, $y=24.0$)
- Door 2: `hall_1` $\leftrightarrow$ `circulation_1` (width: 3.0 ft, horizontal, $y=24.0$)
- Door 3: `circulation_1` $\leftrightarrow$ `kitchen_1` (width: 3.0 ft, horizontal, $y=14.0$)
- Door 4: `circulation_1` $\leftrightarrow$ `bedroom_1` (width: 3.0 ft, vertical, $x=10.0$)
- Door 5: `kitchen_1` $\leftrightarrow$ `pooja_1` (width: 3.0 ft, vertical, $x=18.0$)
- Door 6: `bedroom_1` $\leftrightarrow$ `bathroom_1` (width: 3.0 ft, horizontal, $y=17.0$)
- Door 7: `bedroom_2` $\leftrightarrow$ `bathroom_2` (width: 3.0 ft, horizontal, $y=14.0$)

Every door lies on a genuine shared boundary $\ge 3.0$ ft, connects exactly two adjacent spaces, and preserves a complete connected spanning tree.

---

## 9. Validation Changes
1. `validate_layout`: verifies all rooms are reachable from the entrance via the door graph without disconnected components.
2. `validate_final_circulation_invariants`:
   - Bedrooms: 0 passage violations (removal of bedroom node only disconnects its attached bathroom).
   - Kitchen: 0 passage violations (removal of kitchen node only disconnects pooja).
   - Bathrooms: 0 passage violations (end nodes).
3. `validate_circulation_constraints`:
   - Allows paths traversing `circulation` as legitimate common circulation.

---

## 10. Optimizer Integration
- Optimizers (`expand_rooms`, `optimize_footprint_voids`) explicitly check `if room['type'] in ['parking', 'circulation']: continue`.
- `circulation` is treated as fixed structural geometry during area expansion, ensuring its dimensions, shared edges, and door feasibility are never distorted or invalidated during optimization.

---

## 11. Renderer Integration
In `renderer/svg_renderer.py`:
- `circulation` is rendered as a clean geometric zone filled with pastel tone (`#f0f4c3`) with crisp borders.
- Labeled clearly as `CIRCULATION` with dimension annotations.
- Main entrance and vehicle gate markings remain strictly anchored to Hall and parking boundaries respectively.

---

## 12. Agentic Integration
In `FloorPlanOrchestrator`:
- `LayoutAgent` runs beam search with adaptive circulation fallback.
- `ArchitectureAgent` validates the circulation graph and door placements.
- `ValidationAgent` enforces strict quality gates across geometry, doors, and connectivity.
- `VastuAgent` and `OptimizationAgent` optimize layout without violating circulation boundaries.
- On 25×40 South, the orchestrator achieves `OrchestrationStatus.VALID` with `is_valid: True` in a single pass.

---

## 13. 25×40 South Result
### Status:
`VALID` (Selected topology: `CIRCULATION_SPINE`)

### Generated Geometry:
| Room ID | Type | x (ft) | y (ft) | Width (ft) | Depth (ft) | Area (sq.ft) |
|---|---|---|---|---|---|---|
| `hall_1` | hall | 10.0 | 24.0 | 15.0 | 16.0 | 240.0 |
| `parking_1` | parking | 0.0 | 22.0 | 10.0 | 18.0 | 180.0 |
| `circulation_1` | circulation | 10.0 | 14.0 | 4.0 | 10.0 | 40.0 |
| `bedroom_1` | bedroom | 0.0 | 1.0 | 10.0 | 16.0 | 160.0 |
| `bedroom_2` | bedroom | 14.0 | 14.0 | 11.0 | 10.0 | 110.0 |
| `kitchen_1` | kitchen | 10.0 | 0.0 | 8.0 | 14.0 | 112.0 |
| `pooja_1` | pooja | 18.0 | 1.0 | 7.0 | 8.0 | 56.0 |
| `bathroom_1` | bathroom | 0.0 | 17.0 | 8.0 | 5.0 | 40.0 |
| `bathroom_2` | bathroom | 18.0 | 9.0 | 7.0 | 5.0 | 35.0 |

### Entrance:
- Side: `south`
- Room: `hall_1`
- Coordinates: $x = 15.5$, $y = 40.0$
- Width: $4.0\text{ ft}$
- Validation: `PASS`

### Vehicle Gate:
- Side: `south`
- Room: `parking_1`
- Coordinates: $x = 0.0$, $y = 40.0$
- Width: $10.0\text{ ft}$
- Validation: `PASS`

### Doors (7 valid doors, 0 invalid):
1. `door_1`: `hall_1` $\to$ `bedroom_2`, width: 3.0, horizontal, $(18.0, 24.0)$
2. `door_2`: `hall_1` $\to$ `circulation_1`, width: 3.0, horizontal, $(10.5, 24.0)$
3. `door_3`: `circulation_1` $\to$ `kitchen_1`, width: 3.0, horizontal, $(10.5, 14.0)$
4. `door_4`: `circulation_1` $\to$ `bedroom_1`, width: 3.0, vertical, $(10.0, 14.0)$
5. `door_5`: `kitchen_1` $\to$ `pooja_1`, width: 3.0, vertical, $(18.0, 3.5)$
6. `door_6`: `bedroom_1` $\to$ `bathroom_1`, width: 3.0, horizontal, $(2.5, 17.0)$
7. `door_7`: `bedroom_2` $\to$ `bathroom_2`, width: 3.0, horizontal, $(20.0, 14.0)$

### Connectivity Graph:
```
           EXTERIOR
           /      \
[Vehicle Gate]  [Main Entrance]
         /          \
    parking_1      hall_1
                  /      \
            bedroom_2  circulation_1
               |          /       \
           bathroom_2  bedroom_1  kitchen_1
                          |           |
                      bathroom_1   pooja_1
```

### Privacy Metrics:
- Bedroom passage violations: **0**
- Kitchen passage violations: **0**
- Bathroom passage violations: **0**

---

## 14. Regression Results
### Procedural Regression (`test_cases.py`):
- **TC1** (30×40 West, 2B1H1K2B1P + parking): **PASS** (Star topology preserved, 0 circulation nodes)
- **TC2** (40×50 East, 3B1H1K2B + parking): **PASS** (Star topology preserved, 0 circulation nodes)
- **TC3** (30×50 North, 2B1H2K1B1P + parking): **PASS** (Star topology preserved, 0 circulation nodes)
- **TC4** (30×40 West, 1B1H1K1B + parking): **PASS** (Star topology preserved, 0 circulation nodes)

### Pytest Test Suite:
- **33 passed** out of 33 tests in `pytest tests/ -v`.
- Includes 10 dedicated Phase 4G tests in `tests/test_phase4g_circulation.py`.

### Robustness Evaluation (`tests/evaluate_robustness.py`):
- 26 test scenarios evaluated.
- **25 VALID**, **1 INFEASIBLE_REQUEST** (Plot-20x30, genuinely physically overconstrained).
- **0 invalid plans rendered**.

---

## 15. Adaptivity Demonstration
- **Case A (Spacious plots, e.g. TC1 30×40 West, TC2 40×50 East):**
  - Star topology succeeds directly on Root A.
  - Circulation node count = 0.
  - Preserves traditional direct Hall access.
- **Case B (Constrained plots, e.g. 25×40 South full program):**
  - Star topology evaluates Root A and Root B, both failing due to frontage deficit.
  - Adaptive circulation triggers automatically.
  - 4×10 ft circulation spine placed deterministically.
  - Produces 25 complete, valid candidate plans.

---

## 16. Limitations
1. Circulation width is currently bounded to 4.0 ft; very large multi-story commercial or luxury villa layouts might prefer a grand 6.0 ft distribution gallery.
2. Circulation is currently implemented as a single linear spine or pocket; compound L-shaped or T-shaped corridors are not yet needed for single-family residential plots under 2400 sq.ft.

---

## 17. Final Acceptance Status
**ACCEPTED.** All criteria in Section 36 are met. Adaptive circulation operates strictly as a fallback topology while preserving star topology as preferred.
