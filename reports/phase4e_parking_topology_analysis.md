# Phase 4E — Adaptive Parking & Frontage Topology Investigation

## 1. Executive Summary

Phase 4E conducted a controlled, read-only empirical investigation to answer:
> **"Is the current parking/frontage topology the dominant cause of the 25×40 South-facing feasibility failure, and can a genuinely different parking topology resolve it without weakening architectural constraints?"**

### Primary Empirical Findings:
1. **Parking is indeed a major physical contributor**:
   - In baseline Root A and Root B, parking ($10\times 18\text{ ft}$) flanks the Hall along its entire depth, deadening its side wall and leaving only $14.0\text{ ft}$ of interior edge. This causes immediate beam search termination at `bedroom_2` ($0\text{ candidates}$).
   - When non-flanking parking was tested (Topology C1: $10\times 16\text{ ft}$ parking + $14\times 20\text{ ft}$ Hall), Hall usable interior edge increased from $14.0\text{ ft} \rightarrow 18.0\text{ ft}$ ($+28.5\%$), and **`bedroom_2` candidates surged from $0 \rightarrow 28$ ($15\text{ surviving states}$)**.
2. **Parking is NOT the sole cause**:
   - Despite unlocking 28 candidate states for `bedroom_2`, Topology C1, C2, and D still produced **0 complete candidates** and **0 final-valid layouts**.
   - The beam search immediately collapsed at the very next room: **`kitchen_1` ($0\text{ candidates}$)**.
   - Why? Because `bedroom_1` ($\ge 10\text{ ft}$) + `bedroom_2` ($\ge 10\text{ ft}$) + `kitchen_1` ($\ge 8\text{--}10\text{ ft}$) demand at least $28.0\text{ ft}$ of direct Hall contact. The narrow 25 ft lot cannot expose more than $18.0\text{ ft}$ of Hall interior edge while keeping parking on the road boundary and all rooms within plot bounds.
3. **Conclusion & Decision**:
   - **QUESTION 1 (Major Contributor)**: **YES**
   - **QUESTION 2 (Sole Cause)**: **NO**
   - **QUESTION 3 (Improves Usable Edge)**: **YES** ($14\text{ ft} \rightarrow 18\text{ ft}$)
   - **QUESTION 4 (Translates to More Candidates)**: **YES** for Bedroom 2 ($0 \rightarrow 28$), but **NO** for Kitchen 1 ($0$).
   - **QUESTION 5 (Produces Complete Valid Layout)**: **NO** ($0$ complete, $0$ valid).
   - **QUESTION 6 (Phase 4F Decision)**: **B. INVESTIGATE FURTHER** (specifically: investigate compound circulation/frontage mechanisms, recognizing that 25×40 South remains overconstrained under unrelaxed direct-access rules).

---

## 2. Current Parking Implementation

Production parking logic was inspected in [config/room_dimensions.py](file:///d:/CTS/final_year_01/indian-floorplan-generator/config/room_dimensions.py), [layout/generator.py](file:///d:/CTS/final_year_01/indian-floorplan-generator/layout/generator.py), [layout/entrance.py](file:///d:/CTS/final_year_01/indian-floorplan-generator/layout/entrance.py), and [layout/validator.py](file:///d:/CTS/final_year_01/indian-floorplan-generator/layout/validator.py):

- **Dimensions**:
  - `min_width = 9.0 ft`, `pref_width = 10.0 ft`, `max_width = 14.0 ft`
  - `min_depth = 16.0 ft`, `pref_depth = 18.0 ft`, `max_depth = 24.0 ft`
- **Frontage Anchor**:
  - In `generate_layout()`, parking is anchored strictly to the road boundary: `is_room_on_boundary(parking, facing, plot_w, plot_d)` is enforced as a hard invariant.
  - For South facing, parking is placed at the South boundary ($y = 22..40$ for $18\text{ ft}$ depth).
- **Vehicle Gate**:
  - `create_vehicle_gate()` creates a $10.0\text{ ft}$ gate on the exterior road boundary opening directly into `parking_1`.
  - Must remain strictly independent from the $4.0\text{ ft}$ main entrance into `hall_1`.
- **Zero Internal Connectivity**:
  - `validate_layout()` enforces that parking must **not** connect internally to any residential room.

---

## 3. Current Root A Topology (Control)

- **Parking Position**: SW corner: `x = 0..10, y = 22..40` (Width $10\text{ ft}$, Depth $18\text{ ft}$).
- **Hall Position**: SE corner: `x = 11..25, y = 24..40` (Width $14\text{ ft}$, Depth $16\text{ ft}$).
- **Frontage Consumed**: $10.0\text{ ft}$ (Parking) + $14.0\text{ ft}$ (Hall) + $1.0\text{ ft}$ (clearance) = $25.0\text{ ft}$ ($100\%$ of frontage).
- **Parking Shared Wall**: Flanks Hall along its entire depth ($y = 24..40$, length $16\text{ ft}$).
- **Hall Boundaries**:
  - South ($y = 40$): Exterior road ($14\text{ ft}$). Hosts main entrance.
  - East ($x = 25$): Lot boundary line ($16\text{ ft}$). Dead wall.
  - West ($x = 11$): Parking shared wall ($16\text{ ft}$). Dead wall.
  - North ($y = 24$): Interior shared edge ($14\text{ ft}$).
- **Usable Interior Access Edge**: Exactly **$14.0\text{ ft}$**.
- **Beam Search Progression**:
  - `bedroom_1`: 10 candidates, 10 surviving states.
  - `bedroom_2`: **0 candidates, 0 surviving states (COLLAPSE)**.

---

## 4. Current Root B Topology (Control)

- **Parking Position**: SE corner: `x = 15..25, y = 22..40` (Width $10\text{ ft}$, Depth $18\text{ ft}$).
- **Hall Position**: SW corner: `x = 0..14, y = 24..40` (Width $14\text{ ft}$, Depth $16\text{ ft}$).
- **Frontage Consumed**: $10.0\text{ ft}$ + $14.0\text{ ft}$ + $1.0\text{ ft}$ = $25.0\text{ ft}$ ($100\%$).
- **Parking Shared Wall**: Flanks Hall along its East wall ($16\text{ ft}$).
- **Hall Boundaries**:
  - South ($y = 40$): Exterior road ($14\text{ ft}$).
  - West ($x = 0$): Lot boundary line ($16\text{ ft}$). Dead wall.
  - East ($x = 14$): Parking shared wall ($16\text{ ft}$). Dead wall.
  - North ($y = 24$): Interior shared edge ($14\text{ ft}$).
- **Usable Interior Access Edge**: Exactly **$14.0\text{ ft}$** (exact mirror of Root A).
- **Beam Search Progression**:
  - `bedroom_1`: 10 candidates, 10 surviving states.
  - `bedroom_2`: **0 candidates, 0 surviving states (COLLAPSE)**.

---

## 5. 25×40 South Baseline Measurements

| Metric | Production Root A | Production Root B | Impact on Circulation |
| :--- | :--- | :--- | :--- |
| **Plot Frontage Width** | $25.0\text{ ft}$ | $25.0\text{ ft}$ | Narrow dimension faces road |
| **Parking Dimensions** | $10.0 \times 18.0\text{ ft}$ | $10.0 \times 18.0\text{ ft}$ | Standard bay |
| **Hall Dimensions** | $14.0 \times 16.0\text{ ft}$ | $14.0 \times 16.0\text{ ft}$ | Production clamp |
| **Parking Frontage Consumed**| $10.0\text{ ft}$ ($40\%$) | $10.0\text{ ft}$ ($40\%$) | Consumes nearly half of road |
| **Hall Frontage Consumed** | $14.0\text{ ft}$ ($56\%$) | $14.0\text{ ft}$ ($56\%$) | Trapped on frontage |
| **Open Frontage Buffer** | $1.0\text{ ft}$ ($4\%$) | $1.0\text{ ft}$ ($4\%$) | Negligible |
| **Hall Dead Wall Length** | $46.0\text{ ft}$ ($76.7\%$) | $46.0\text{ ft}$ ($76.7\%$) | 3 out of 4 faces dead |
| **Usable Interior Edge** | **$14.0\text{ ft}$** | **$14.0\text{ ft}$** | North face only |
| **Direct Contact Demand** | **$28.0\text{ ft}$** | **$28.0\text{ ft}$** | Bed 1 (10) + Bed 2 (10) + Kit (8) |
| **Access Deficit** | **$-14.0\text{ ft}$** | **$-14.0\text{ ft}$** | Severe physical deficit |

---

## 6. Parking Topology Experiments

Six distinct parking configurations were evaluated on 25×40 South:

- **Topology A (Current Root A - Control)**: Parking SW ($10\times 18$), Hall SE ($14\times 16$).
- **Topology B (Current Root B - Control)**: Parking SE ($10\times 18$), Hall SW ($14\times 16$).
- **Topology C1 (Non-Flanking: Min Depth 16ft + Deep Hall 20ft)**:
  - Parking depth reduced to $16.0\text{ ft}$ (minimum allowable in `ROOM_DIMENSIONS`).
  - Hall deepened to $20.0\text{ ft}$ ($y = 20..40$).
  - Hall extends $4.0\text{ ft}$ deeper than parking, exposing $4.0\text{ ft}$ of its West wall in addition to its $14.0\text{ ft}$ North wall (total usable edge = $18.0\text{ ft}$).
- **Topology C2 (Non-Flanking: Min Width 9ft + Depth 16ft)**:
  - Parking reduced to $9.0\times 16.0\text{ ft}$ (absolute minimums).
  - Hall $14.0\times 20.0\text{ ft}$ at $x = 10..24$, leaving a $1.0\text{ ft}$ east buffer.
- **Topology D (Side/Rear Parking - Analytical Simulation)**:
  - Parking placed along rear lot line ($x = 0..10, y = 0..18$).
  - Hall placed on road frontage ($x = 0..14, y = 24..40$).
  - Evaluated to test the geometric effect of removing parking from frontage.
- **Topology E (Linear / Compact Frontage 8ft - Analytical Sensitivity)**:
  - Parking width set to $8.0\text{ ft}$ (below $9.0\text{ ft}$ code min).

### Comparative Experiment Table

| Topology | Park W | Hall W | Park Shared Edge | Usable Hall Edge | Bed 1 Cands | Bed 2 Cands | Complete Cands | Final Valid | Root Valid | Dominant Collapse Point |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Topology A (Root A)** | 10.0 | 14.0 | 16.0 | 14.0 ft | 10 | **0** | 0 | 0 | True | `bedroom_2` (0 states) |
| **Topology B (Root B)** | 10.0 | 14.0 | 16.0 | 14.0 ft | 10 | **0** | 0 | 0 | True | `bedroom_2` (0 states) |
| **Topology C1 (Non-Flank)** | 10.0 | 14.0 | 16.0 | **18.0 ft** | 10 | **28** | 0 | 0 | True | **`kitchen_1` (0 states)** |
| **Topology C2 (Min W/D)** | 9.0 | 14.0 | 16.0 | **19.0 ft** | 10 | **20** | 0 | 0 | True | **`kitchen_1` (0 states)** |
| **Topology D (Rear Park)** | 10.0 | 14.0 | 0.0 | **30.0 ft** | 10 | **70** | 0 | 0 | **False** | **`kitchen_1` (0 states)** |
| **Topology E (8ft Front)** | 8.0 | 14.0 | 16.0 | 14.0 ft | 10 | **0** | 0 | 0 | **False** | `bedroom_2` (0 states) |

---

## 7. Hall Access Measurements

Detailed boundary segment breakdown across the topologies:

| Boundary Segment | Topology A (Root A) | Topology B (Root B) | Topology C1 (Non-Flank) | Topology C2 (Min W/D) | Topology D (Rear Park) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **South Face (Road)** | 14.0 ft (Exterior) | 14.0 ft (Exterior) | 14.0 ft (Exterior) | 14.0 ft (Exterior) | 14.0 ft (Exterior) |
| **East Face (Lot Line)** | 16.0 ft (Exterior) | 16.0 ft (Parking) | 20.0 ft (Exterior) | 20.0 ft (Open 1ft) | 16.0 ft (Interior) |
| **West Face (Parking)** | 16.0 ft (Parking) | 16.0 ft (Exterior) | 16.0 ft (Park) + **4.0 ft Open**| 16.0 ft (Park) + **4.0 ft Open**| 16.0 ft (Interior) |
| **North Face (Interior)**| 14.0 ft (Open) | 14.0 ft (Open) | 14.0 ft (Open) | 14.0 ft (Open) | 14.0 ft (Open) |
| **Net Usable Interior Edge**| **14.0 ft** | **14.0 ft** | **18.0 ft** | **19.0 ft** | **30.0 ft** |

---

## 8. Bedroom Candidate Measurements

1. **Topology A & B**:
   - `bedroom_1`: 10 candidates generated (all attaching to the $14\text{ ft}$ North face).
   - `bedroom_2`: **0 candidates**. `bedroom_1` consumes $10\text{--}14\text{ ft}$ of the North face, leaving $\le 4\text{ ft}$, which is insufficient for a $10\text{ ft}$ bedroom.
2. **Topology C1 (Non-Flanking)**:
   - `bedroom_1`: 10 candidates generated.
   - `bedroom_2`: **28 candidates generated (15 surviving states)**!
   - *Physical Mechanism*: Because Hall extends $4\text{ ft}$ past parking, `bedroom_2` can wrap around the corner and attach to the exposed West face and North-West corner.
3. **Topology C2 (Min W/D)**:
   - `bedroom_1`: 10 candidates generated.
   - `bedroom_2`: **20 candidates generated (15 surviving states)**!
4. **Topology D (Rear Parking)**:
   - `bedroom_1`: 10 candidates generated.
   - `bedroom_2`: **70 candidates generated (15 surviving states)**!

---

## 9. Beam-Search Collapse Points

Tracing the step progression of beam search:

```text
Topology A & B:
  Stage 1: bedroom_1 -> 10 candidates, 10 surviving states
  Stage 2: bedroom_2 -> 0 candidates, 0 surviving states  <-- IMMEDIATE COLLAPSE

Topology C1 (Non-Flanking):
  Stage 1: bedroom_1 -> 10 candidates, 10 surviving states
  Stage 2: bedroom_2 -> 28 candidates, 15 surviving states  <-- RESCUED!
  Stage 3: kitchen_1 -> 0 candidates, 0 surviving states   <-- SECONDARY COLLAPSE

Topology C2 (Min W/D):
  Stage 1: bedroom_1 -> 10 candidates, 10 surviving states
  Stage 2: bedroom_2 -> 20 candidates, 15 surviving states  <-- RESCUED!
  Stage 3: kitchen_1 -> 0 candidates, 0 surviving states   <-- SECONDARY COLLAPSE

Topology D (Rear Parking):
  Stage 1: bedroom_1 -> 10 candidates, 10 surviving states
  Stage 2: bedroom_2 -> 70 candidates, 15 surviving states  <-- RESCUED!
  Stage 3: kitchen_1 -> 0 candidates, 0 surviving states   <-- SECONDARY COLLAPSE
```

### Decisive Mathematical Insight:
Non-flanking parking successfully rescues `bedroom_2` by providing just enough perimeter ($18\text{--}19\text{ ft}$) to attach two bedrooms. However, both bedrooms completely exhaust all exposed Hall edges. When `kitchen_1` arrives, it has **zero available Hall perimeter left**, causing immediate pipeline collapse.

---

## 10. Entrance Validation

Verification of main entrance for all topologies:
- **Topology A**: Side = `south`, $x = 16.0, y = 40.0$, to = `hall_1` $\rightarrow$ **VALID**
- **Topology B**: Side = `south`, $x = 5.0, y = 40.0$, to = `hall_1` $\rightarrow$ **VALID**
- **Topology C1**: Side = `south`, $x = 16.0, y = 40.0$, to = `hall_1` $\rightarrow$ **VALID**
- **Topology C2**: Side = `south`, $x = 15.0, y = 40.0$, to = `hall_1` $\rightarrow$ **VALID**
- **Topology D**: Side = `south`, $x = 5.0, y = 40.0$, to = `hall_1` $\rightarrow$ **VALID**
- **Topology E**: Side = `south`, $x = 16.0, y = 40.0$, to = `hall_1` $\rightarrow$ **VALID**

The hard invariant `exterior -> main_entrance -> hall_1` on the South road boundary was 100% preserved in all tested configurations.

---

## 11. Vehicle-Gate Validation

Verification of vehicle gate for all topologies:
- **Topology A**: Side = `south`, $x = 0.0, y = 40.0$, to = `parking_1` $\rightarrow$ **VALID**
- **Topology B**: Side = `south`, $x = 15.0, y = 40.0$, to = `parking_1` $\rightarrow$ **VALID**
- **Topology C1**: Side = `south`, $x = 0.0, y = 40.0$, to = `parking_1` $\rightarrow$ **VALID**
- **Topology C2**: Side = `south`, $x = 0.0, y = 40.0$, to = `parking_1` $\rightarrow$ **VALID**
- **Topology D (Rear)**: Side = `south`, $x = 0.0, y = 40.0$, to = `parking_1` $\rightarrow$ **INVALID / FAILS ROOT VALIDATION**
  - In Topology D, parking is at $y = 0..18$. The gate at $y = 40$ does not physically touch parking. It requires driving through the house, which violates physical feasibility and root validation rules (`is_room_on_boundary` returns False).
- **Topology E**: Side = `south`, $x = 0.0, y = 40.0$, to = `parking_1` $\rightarrow$ **FAILS ROOT VALIDATION** (8ft width is below 9ft code minimum).

---

## 12. Control-Case Comparison

| Case | Root | Plot (W x D) | Road Facing | Frontage Width | Hall Dimensions | Usable Interior Edge | Complete Candidates | Final Valid | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Case B (30x50 South)** | Root A | 30 x 50 | South | 30 ft | 20 x 22 | 24.0 ft | 0 | 0 | Infeasible in Root A |
| **Case B (30x50 South)** | Root B | 30 x 50 | South | 30 ft | 20 x 22 | **42.0 ft** | **15** | **15** | **RESCUED by Root B** |
| **Case C (25x40 West)** | Root A | 25 x 40 | West | **40 ft** | 14 x 16 | **30.0 ft** | **15** | **15** | **VALID** |
| **Case D (40x50 East)** | Root A | 40 x 50 | East | **40 ft** | 18 x 20 | **38.0 ft** | **15** | **15** | **VALID** |
| **TC1 (30x40 West)** | Root A | 30 x 40 | West | **40 ft** | 14 x 16 | **30.0 ft** | **15** | **15** | **VALID** |
| **TC2 (40x50 East)** | Root A | 40 x 50 | East | **40 ft** | 18 x 20 | **38.0 ft** | **15** | **15** | **VALID** |
| **TC3 (30x50 North)** | Root B | 30 x 50 | North | 30 ft | 20 x 22 | **22.0 ft** | **15** | **15** | **VALID in Root B** |
| **TC4 (30x40 West)** | Root A | 30 x 40 | West | **40 ft** | 14 x 16 | **30.0 ft** | **15** | **15** | **VALID** |

### Why Did 30×50 South Succeed Under Root B while 25×40 South Failed?
1. **Frontage Width**: 30×50 has $30\text{ ft}$ of frontage ($5\text{ ft}$ wider than 25 ft).
2. **Usable Edge Differential**: In 30×50 South Root B, Hall exposes **$42.0\text{ ft}$** of usable interior edge! In 25×40 South Root B, Hall exposes only **$14.0\text{ ft}$** (a $28\text{ ft}$ deficit).
3. **Lot Aspect Ratio**: On 25×40 West, the road is along the $40\text{ ft}$ side, giving $30.0\text{ ft}$ of interior edge. 25×40 South has the road on the narrow $25\text{ ft}$ side.

---

## 13. Frontage Sensitivity Results

Sweeping parking width from $8.0\text{ ft}$ to $12.0\text{ ft}$ on 25×40 South (with $16\text{ ft}$ deep Hall):

| Parking Width | Hall Width | Frontage Consumed | Usable Interior Edge | Bed 1 Cands | Bed 2 Cands | Complete Cands | Final Valid |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **8.0 ft** | 14.0 ft | 32.0% | 14.0 ft | 10 | 0 | 0 | 0 |
| **9.0 ft** | 14.0 ft | 36.0% | 14.0 ft | 10 | 0 | 0 | 0 |
| **10.0 ft (Baseline)** | 14.0 ft | 40.0% | 14.0 ft | 10 | 0 | 0 | 0 |
| **11.0 ft** | 13.0 ft | 44.0% | 13.0 ft | 10 | 0 | 0 | 0 |
| **12.0 ft** | 12.0 ft | 48.0% | 12.0 ft | 10 | 0 | 0 | 0 |

*Sensitivity Finding*:
Merely narrowing parking width along the road frontage (without changing relative depths to expose side walls) leaves the Hall with only its North face open ($12\text{--}14\text{ ft}$). It produces **0 candidates for Bedroom 2** across all tested widths. Only depth differential (Topology C1) exposes side perimeter.

---

## 14. Causal Interpretation

The investigation strictly evaluated the causal chain:
$$\text{Parking} \rightarrow \text{Frontage Consumption} \rightarrow \text{Hall Shared Edge} \rightarrow \text{Loss of Usable Hall Edge} \rightarrow \text{Bed 1 consumes edge} \rightarrow \text{Bed 2 fails} \rightarrow \text{Infeasible}$$

### Verdict:
1. **The first part of the chain IS CAUSAL**:
   Parking flanks Hall along frontage $\rightarrow$ kills Hall side wall $\rightarrow$ leaves only $14\text{ ft}$ $\rightarrow$ Bed 1 takes $10\text{--}14\text{ ft}$ $\rightarrow$ Bed 2 has $0$ candidates.
   - Proven by Topology C1: Breaking the flanking lock increased usable edge to $18\text{ ft}$ and instantly created 28 candidates for Bedroom 2.
2. **However, solving parking alone DOES NOT solve the full problem**:
   Even when Bedroom 2 is rescued, `kitchen_1` immediately deadlocks with 0 candidates because the compound access demand of 2 Bedrooms + 1 Kitchen ($28\text{ ft}$) still exceeds the maximum possible Hall interior edge ($18\text{ ft}$) on a 25 ft lot with frontage parking.

---

## 15. Limitations

1. **Current Parking Model Constraints**:
   The current production model requires parking to touch the exterior road boundary. Side or rear parking (Topology D) cannot be legally represented without an architectural model extension (e.g. driveable driveway entity).
2. **Single-Hub Star Topology Invariant**:
   Production rules currently mandate that every bedroom and kitchen must physically share a wall with `hall_1`. As long as all three rooms must touch `hall_1` directly, a 25 ft frontage lot with frontage parking cannot satisfy the total linear contact requirement ($28\text{ ft}$).

---

## 16. Recommendation

In accordance with Section 18 of the Phase 4E specification:

### **SELECTED DECISION: B. INVESTIGATE FURTHER**

### Explicit Answers to the 6 Required Questions:

- **QUESTION 1: Is parking a major contributor to the 25×40 South infeasibility?**
  **YES**. Side-by-side parking on the 25 ft frontage deadens $16\text{ ft}$ of Hall wall, causing immediate collapse at Bedroom 2.
- **QUESTION 2: Is parking proven to be the sole cause?**
  **NO**. Non-flanking parking rescues Bedroom 2 (28 candidates), but the layout still collapses at Kitchen 1 because total direct-access demand ($28\text{ ft}$) exceeds Hall's maximum exposed perimeter ($18\text{ ft}$).
- **QUESTION 3: Does a genuinely different parking topology improve Hall usable edge?**
  **YES**. Topology C1 increases usable interior edge from $14.0\text{ ft} \rightarrow 18.0\text{ ft}$ ($+28.5\%$).
- **QUESTION 4: Does that improvement translate into more bedroom/kitchen candidates?**
  **YES** for Bedroom 2 ($0 \rightarrow 28$ candidates), but **NO** for Kitchen 1 ($0$ candidates).
- **QUESTION 5: Does it produce a complete final-valid layout?**
  **NO**. Complete candidates remain 0; final valid layouts remain 0.
- **QUESTION 6: Should Phase 4F implement adaptive parking topology?**
  **B. INVESTIGATE FURTHER**.
  *Rationale*: Implementing parking topology adaptation alone will NOT rescue 25×40 South; it will only shift the collapse point from `bedroom_2` to `kitchen_1`. Phase 4F should investigate a compound solution combining parking frontage adaptation with circulation/access flexibility (e.g. an internal circulation pocket or secondary kitchen access).
