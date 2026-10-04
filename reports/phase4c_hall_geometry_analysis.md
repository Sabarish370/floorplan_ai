# Phase 4C — Hall Geometry Investigation

## 1. Objective

The primary objective of Phase 4C is to conduct a rigorous, evidence-based investigation to answer:
> **"Is the current Hall geometry/topology the primary structural bottleneck preventing valid layouts for the 25x40 South case?"**

In Phase 4B, adaptive root topology generation (Root A vs Root B) was implemented, successfully rescuing the 30x50 South scenario. However, 25x40 South, 25x40 North, and 25x40 East remained infeasible. This investigation evaluates whether altering Hall aspect ratio or geometry alone can unlock valid layouts for 25x40 South under all active architectural, circulation, door feasibility, and entrance invariants, or whether other structural constraints dominate.

---

## 2. Current Hall Generation Logic

A comprehensive technical trace of Hall generation through the production pipeline reveals the exact mechanics:

### Pipeline Execution Flow
```text
Plot Dimensions & Facing
  ↓ [generate_layout()]
Orientation Setup & Bounds
  ↓ [_compute_adaptive_roots() / _build_root_topology()]
Parking Placement (dimensions & corner anchor)
  ↓ [_select_hall_dimensions()]
Hall Sizing (width, depth from plot & facing)
  ↓ [_place_hall()]
Hall Positioning (corner anchor adjacent/opposite parking on frontage)
  ↓ [generate_candidates()]
Beam Search Candidate Generation
  ↓ [generate_internal_doors()]
Door Placement & Shared-Edge Calculation
  ↓ [validate_layout_strict() & validate_circulation()]
Validation & Feasibility Gates
```

### Detailed Trace Responses (Section 4 Requirements)
1. **Where Hall dimensions are selected:**
   In [layout/generator.py](file:///d:/CTS/final_year_01/indian-floorplan-generator/layout/generator.py), inside `_select_hall_dimensions(plot_w, plot_d, facing)`.
2. **How Hall width is calculated:**
   - For North/South facing: `hall_w = round(plot_w * 0.40)` (clamped between 14 ft and 20 ft).
   - For East/West facing: `hall_w = round(plot_w * 0.45)` (clamped between 14 ft and 18 ft).
3. **How Hall depth is calculated:**
   - For North/South facing: `hall_d = round(plot_d * 0.40)` (clamped between 16 ft and 22 ft).
   - For East/West facing: `hall_d = round(plot_d * 0.40)` (clamped between 16 ft and 22 ft).
4. **Whether dimensions depend on plot dimensions:**
   Yes, proportional to plot width and depth ($40\%\text{--}45\%$), bounded by explicit minimum and maximum clamps.
5. **Minimum Hall dimensions:**
   Absolute minimums in code: Width $\ge 10\text{ ft}$ (in dimension validator), clamp minimum in generator is $14\text{ ft}$. Depth minimum clamp is $16\text{ ft}$.
6. **Maximum Hall dimensions:**
   Width maximum clamp is $20\text{ ft}$ (N/S) or $18\text{ ft}$ (E/W). Depth maximum clamp is $22\text{ ft}$.
7. **Whether Hall dimensions are rounded:**
   Yes, rounded to integer feet using Python's `round()`.
8. **How Hall position is selected:**
   Anchored along the frontage boundary matching `facing`.
   - In South-facing Root A: Parking occupies the SW corner (`x = 0..10, y = 0..15`), leaving Hall placed at the SE corner (`x = 11..25, y = 0..16`).
   - In South-facing Root B: Parking occupies the SE corner (`x = 15..25, y = 0..15`), leaving Hall placed at the SW corner (`x = 0..14, y = 0..16`).
9. **How Hall frontage is determined:**
   Hall boundary segment collinear with the plot frontage edge (for South facing, `y = 0`). Hall frontage width equals Hall width (14 ft in baseline).
10. **How Hall exterior boundary is calculated:**
    Intersection of Hall bounding box segments with plot perimeter (`x = 0`, `x = plot_w`, `y = 0`, or `y = plot_d`).
11. **How Hall interior shared boundaries are calculated:**
    Hall boundary segments strictly inside the plot bounding box (`0 < x < plot_w` and `0 < y < plot_d`) that do not overlap parking.
12. **How Hall-to-room direct-access requirements are enforced:**
    In [layout/architecture.py](file:///d:/CTS/final_year_01/indian-floorplan-generator/layout/architecture.py) (`validate_circulation`) and [layout/validator.py](file:///d:/CTS/final_year_01/indian-floorplan-generator/layout/validator.py). Every bedroom and kitchen requires direct access to Hall. Bathrooms may connect to Hall or an attached bedroom.
13. **How Hall doors are generated:**
    In [layout/doors.py](file:///d:/CTS/final_year_01/indian-floorplan-generator/layout/doors.py) (`generate_internal_doors`). Doors require a shared edge length $\ge 3.0\text{ ft}$ (with standard door width $3.0\text{ ft}$).
14. **How Hall entrance feasibility is validated:**
    In [layout/validator.py](file:///d:/CTS/final_year_01/indian-floorplan-generator/layout/validator.py) (`validate_entrance`). Hard check that main entrance is on plot boundary, directly on Hall boundary, on the facing side, width $\ge 3.0\text{ ft}$, with no intermediate room.
15. **Whether Hall geometry is fixed before room beam search:**
    Yes, Hall geometry and position are completely fixed as part of the root layout before beam search candidate generation begins.
16. **Which dimensions are immutable after root generation:**
    Hall width, Hall depth, Hall coordinates $(x_1, y_1, x_2, y_2)$, parking dimensions, and parking coordinates are completely immutable during beam search.

---

## 3. Current Hall Geometry Measurements

Measurements across baseline test cases and controls:

| Case | Plot & Facing | Hall Dimensions | Area (sq ft) | Ext Boundary (ft) | Int Shared Boundary (ft) | Usable Access Edge (ft) | Baseline Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Case A** | 25x40 South | 14.0 x 16.0 | 224.0 | 14.0 (front) + 16.0 (side) | 30.0 | 30.0 | **Infeasible** |
| **Case B** | 30x50 South | 20.0 x 22.0 | 440.0 | 20.0 (front) + 22.0 (side) | 24.0 | 24.0 | **Valid (Root B)** |
| **Case C** | 25x40 West | 14.0 x 16.0 | 224.0 | 16.0 (front) | 34.0 | 34.0 | **Valid** |
| **Case D** | 40x50 East | 18.0 x 20.0 | 360.0 | 20.0 (front) | 46.0 | 46.0 | **Valid** |
| **TC1** | 30x40 West | 14.0 x 16.0 | 224.0 | 16.0 (front) | 34.0 | 34.0 | **Valid** |
| **TC2** | 40x50 East | 18.0 x 20.0 | 360.0 | 20.0 (front) | 46.0 | 46.0 | **Valid** |
| **TC3** | 30x50 North | 20.0 x 22.0 | 440.0 | 20.0 (front) | 24.0 | 24.0 | **Valid** |
| **TC4** | 30x40 West | 14.0 x 16.0 | 224.0 | 16.0 (front) | 34.0 | 34.0 | **Valid** |

*Note: In 25x40 South, Hall shares its exterior side with the plot boundary (x=25 in Root A, x=0 in Root B) and its front with the road (y=0). In West-facing 25x40, the Hall is positioned along the 40 ft depth, leaving greater unobstructed interior boundaries.*

---

## 4. 25x40 South Failure Analysis

In 25x40 South (Plot width = 25 ft, depth = 40 ft, South road at $y = 0$):
- **Parking footprint**: $10.0\text{ ft wide} \times 14.0\text{ ft deep}$ (or $15.0\text{ ft deep}$).
- **Total frontage available**: Exactly $25.0\text{ ft}$.
- Parking consumes $10.0\text{ ft}$ of frontage.
- Hall consumes $14.0\text{ ft}$ (leaving $1.0\text{ ft}$ clearance) or the remaining $15.0\text{ ft}$.
- Therefore, **the entire road frontage ($25\text{ ft}$) is completely consumed by Parking + Hall**.
- Because Hall is anchored against the plot boundary on the East ($x = 25$) in Root A:
  - Hall East edge ($16\text{ ft}$ long) is flush against the lot line. **Zero rooms can attach to East.**
  - Hall South edge ($14\text{ ft}$ long) is on the exterior road. **Zero internal rooms can attach to South.**
  - Hall West edge ($16\text{ ft}$ long) directly abuts Parking ($y = 0..15$). The remaining edge above parking is only $1.0\text{ ft}$ ($y = 15..16$), which is strictly less than the minimum room width ($10.0\text{ ft}$) and minimum door width ($3.0\text{ ft}$).
  - Hall North edge ($14\text{ ft}$ long) is the **ONLY interior edge available for room placement**.

### Mathematical Bottleneck
The room program requires:
- `bedroom_1`: min width $10.0\text{ ft}$, min depth $10.0\text{ ft}$
- `bedroom_2`: min width $10.0\text{ ft}$, min depth $10.0\text{ ft}$
- `kitchen_1`: min width $8.0\text{ ft}$, min depth $8.0\text{ ft}$
- All three rooms **strictly require direct access to Hall**.

To connect directly to Hall, each room must share an edge segment $\ge 3.0\text{ ft}$ with Hall without overlapping each other or parking.
Since the Hall has **only one usable interior edge (North edge = 14 ft)**:
- Placed room 1 (`bedroom_1`, width $\ge 10\text{ ft}$) consumes $10\text{ to }14\text{ ft}$ of the $14\text{ ft}$ North edge.
- Remaining North edge length = $14 - 10 = 4\text{ ft}$ (or $0\text{ ft}$).
- `bedroom_2` (min width $10.0\text{ ft}$) **CANNOT fit on the remaining 4 ft of North edge**.
- `bedroom_2` cannot attach to East (plot line), South (road), or West (parking/1 ft clearance).
- Result: **0 candidates generated for `bedroom_2`**.

---

## 5. Root A Analysis

- **Parking Position**: SW corner: `x = 0..10, y = 0..15`.
- **Hall Position**: SE corner: `x = 11..25, y = 0..16`.
- **Hall Boundaries**:
  - South ($14\text{ ft}$): Exterior road (frontage). Hosts main entrance.
  - East ($16\text{ ft}$): Plot boundary. Inaccessible for rooms.
  - West ($16\text{ ft}$): Abuts parking ($0..15\text{ ft}$). Usable gap above parking: $1\text{ ft}$ ($y = 15..16$). Infeasible for rooms.
  - North ($14\text{ ft}$): Interior shared edge.
- **Total usable room-attaching edge**: Exactly **$14.0\text{ ft}$**.
- **Result**:
  - `bedroom_1` candidates generated: 14 states (all anchored to North edge `y = 16`).
  - `bedroom_2` candidates generated: **0 states**.
  - Pipeline termination: Immediate failure at stage 2 of beam search (`bedroom_2`).

---

## 6. Root B Analysis

- **Parking Position**: SE corner: `x = 15..25, y = 0..15`.
- **Hall Position**: SW corner: `x = 0..14, y = 0..16`.
- **Hall Boundaries**:
  - South ($14\text{ ft}$): Exterior road (frontage). Hosts main entrance.
  - West ($16\text{ ft}$): Plot boundary. Inaccessible for rooms.
  - East ($16\text{ ft}$): Abuts parking ($0..15\text{ ft}$). Usable gap above parking: $1\text{ ft}$ ($y = 15..16$). Infeasible for rooms.
  - North ($14\text{ ft}$): Interior shared edge.
- **Total usable room-attaching edge**: Exactly **$14.0\text{ ft}$** (mirror of Root A).
- **Result**:
  - `bedroom_1` candidates generated: 14 states.
  - `bedroom_2` candidates generated: **0 states**.
  - Pipeline termination: Immediate failure at stage 2 of beam search (`bedroom_2`).

Root B produces an exact geometric mirror along the narrow 25 ft frontage; hence, flipping parking from West to East provides zero additional interior edge.

---

## 7. Hall Geometry Variants

To test whether modifying Hall dimensions can solve the access deficit, 8 controlled Hall variants were evaluated against both Root A and Root B:

- **Variant 0 (Production Baseline)**: Width $14.0\text{ ft}$, Depth $16.0\text{ ft}$ (Area $224\text{ sq ft}$).
- **Variant 1 (Inverted Aspect Ratio)**: Width $15.0\text{ ft}$, Depth $14.0\text{ ft}$ (Area $210\text{ sq ft}$).
- **Variant 2 (Wider + Shallower)**: Width $14.0\text{ ft}$, Depth $14.0\text{ ft}$ (Area $196\text{ sq ft}$).
- **Variant 3 (Narrower + Deeper)**: Width $12.0\text{ ft}$, Depth $20.0\text{ ft}$ (Area $240\text{ sq ft}$). Extends $5\text{ ft}$ past parking.
- **Variant 4 (Minimum Width)**: Width $10.0\text{ ft}$, Depth $20.0\text{ ft}$ (Area $200\text{ sq ft}$). Extends $5\text{ ft}$ past parking.
- **Variant 5 (Moderately Deeper)**: Width $14.0\text{ ft}$, Depth $18.0\text{ ft}$ (Area $252\text{ sq ft}$). Extends $3\text{ ft}$ past parking.
- **Variant 6 (Area-Preserving Aspect)**: Width $12.0\text{ ft}$, Depth $18.0\text{ ft}$ (Area $216\text{ sq ft}$). Extends $3\text{ ft}$ past parking.
- **Variant 7 (Max Usable Perimeter)**: Width $10.0\text{ ft}$, Depth $22.0\text{ ft}$ (Area $220\text{ sq ft}$). Extends $7\text{ ft}$ past parking.
- **Variant 7b (Max Area Elongated)**: Width $12.0\text{ ft}$, Depth $22.0\text{ ft}$ (Area $264\text{ sq ft}$). Extends $7\text{ ft}$ past parking.

---

## 8. Controlled Experiment Results

### Experiment 1: Hall Geometry Variants on 25x40 South

| Variant | Root | Hall W | Hall D | Hall Area | Interior Edge | Usable Access Edge | Door-Feasible Edge | Complete Candidates | Valid Layouts | Dominant Failure |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **V0 (Baseline)** | Root A | 14.0 | 16.0 | 224.0 | 30.0 | 30.0 | 14.0 | 0 | 0 | `HALL_ACCESS` (`bedroom_2`: 0) |
| **V0 (Baseline)** | Root B | 14.0 | 16.0 | 224.0 | 30.0 | 30.0 | 14.0 | 0 | 0 | `HALL_ACCESS` (`bedroom_2`: 0) |
| **V1 (Inverted)** | Root A | 15.0 | 14.0 | 210.0 | 15.0 | 15.0 | 15.0 | 0 | 0 | `HALL_ACCESS` (`bedroom_2`: 0) |
| **V1 (Inverted)** | Root B | 15.0 | 14.0 | 210.0 | 15.0 | 15.0 | 15.0 | 0 | 0 | `HALL_ACCESS` (`bedroom_2`: 0) |
| **V2 (Wider)** | Root A | 14.0 | 14.0 | 196.0 | 28.0 | 28.0 | 14.0 | 0 | 0 | `HALL_ACCESS` (`bedroom_2`: 0) |
| **V2 (Wider)** | Root B | 14.0 | 14.0 | 196.0 | 28.0 | 28.0 | 14.0 | 0 | 0 | `HALL_ACCESS` (`bedroom_2`: 0) |
| **V3 (Narrow/Deep)**| Root A | 12.0 | 20.0 | 240.0 | 34.0 | 32.0 | 17.0 | 0 | 0 | `HALL_ACCESS` (`bedroom_2`: 0) |
| **V3 (Narrow/Deep)**| Root B | 12.0 | 20.0 | 240.0 | 32.0 | 32.0 | 17.0 | 0 | 0 | `HALL_ACCESS` (`bedroom_2`: 0) |
| **V4 (Min Width)** | Root A | 10.0 | 20.0 | 200.0 | 32.0 | 30.0 | 15.0 | 0 | 0 | `HALL_ACCESS` (`bedroom_2`: 0) |
| **V4 (Min Width)** | Root B | 10.0 | 20.0 | 200.0 | 30.0 | 30.0 | 15.0 | 0 | 0 | `HALL_ACCESS` (`bedroom_2`: 0) |
| **V5 (Mod Deep)** | Root A | 14.0 | 18.0 | 252.0 | 32.0 | 32.0 | 17.0 | 0 | 0 | `HALL_ACCESS` (`bedroom_2`: 0) |
| **V5 (Mod Deep)** | Root B | 14.0 | 18.0 | 252.0 | 32.0 | 32.0 | 17.0 | 0 | 0 | `HALL_ACCESS` (`bedroom_2`: 0) |
| **V6 (Area Pres)** | Root A | 12.0 | 18.0 | 216.0 | 30.0 | 30.0 | 15.0 | 0 | 0 | `HALL_ACCESS` (`bedroom_2`: 0) |
| **V6 (Area Pres)** | Root B | 12.0 | 18.0 | 216.0 | 30.0 | 30.0 | 15.0 | 0 | 0 | `HALL_ACCESS` (`bedroom_2`: 0) |
| **V7 (Max Edge)** | Root A | 10.0 | 22.0 | 220.0 | 36.0 | 36.0 | 17.0 | 0 | 0 | `HALL_ACCESS` (Bed2 passes, `kitchen_1`: 0) |
| **V7 (Max Edge)** | Root B | 10.0 | 22.0 | 220.0 | 32.0 | 32.0 | 17.0 | 0 | 0 | `HALL_ACCESS` (Bed2 passes, `kitchen_1`: 0) |
| **V7b (Max Elong)** | Root A | 12.0 | 22.0 | 264.0 | 38.0 | 38.0 | 19.0 | 0 | 0 | `HALL_ACCESS` (`bedroom_2`: 0) |
| **V7b (Max Elong)** | Root B | 12.0 | 22.0 | 264.0 | 34.0 | 34.0 | 19.0 | 0 | 0 | `HALL_ACCESS` (`bedroom_2`: 0) |

### Failure Table

| Case | Root | Hall Variant | Dominant Failure | Evidence |
| :--- | :--- | :--- | :--- | :--- |
| 25x40 South | Root A | V0 (Baseline 14x16) | `HALL_ACCESS` | North edge (14 ft) fully occupied by Bed 1; Bed 2 has 0 candidates. |
| 25x40 South | Root B | V0 (Baseline 14x16) | `HALL_ACCESS` | Mirror of Root A; Bed 2 has 0 candidates. |
| 25x40 South | Root A/B | V1 (Inverted 15x14) | `HALL_ACCESS` | Depth 14 ft is flush with parking depth; only 15 ft North edge available. |
| 25x40 South | Root A/B | V2 (Square 14x14) | `HALL_ACCESS` | Flush with parking depth; only 14 ft North edge available. |
| 25x40 South | Root A/B | V3 (12x20) | `HALL_ACCESS` | West edge past parking is only 5 ft ($20-15$); Bed 2 needs 10 ft; 0 candidates. |
| 25x40 South | Root A/B | V4 (10x20) | `HALL_ACCESS` | West edge past parking is only 5 ft; Bed 2 needs 10 ft; 0 candidates. |
| 25x40 South | Root A/B | V5 (14x18) | `HALL_ACCESS` | West edge past parking is only 3 ft; Bed 2 needs 10 ft; 0 candidates. |
| 25x40 South | Root A/B | V6 (12x18) | `HALL_ACCESS` | West edge past parking is only 3 ft; Bed 2 needs 10 ft; 0 candidates. |
| 25x40 South | Root A/B | V7 (10x22) | `HALL_ACCESS` | North edge (10 ft) + West edge (7 ft) allows Bed 2 (12 states), but then Kitchen 1 has 0 candidates! |
| 25x40 South | Root A/B | V7b (12x22) | `HALL_ACCESS` | West edge past parking (7 ft) cannot fit 10 ft Bed 2; 0 candidates. |

---

## 9. Room-Specific Access Analysis

The production architectural rules enforce the following circulation graph:
- `bedroom_1` $\rightarrow$ `hall_1` (MANDATORY DIRECT ACCESS; cannot pass through another room)
- `bedroom_2` $\rightarrow$ `hall_1` (MANDATORY DIRECT ACCESS; cannot pass through another room)
- `kitchen_1` $\rightarrow$ `hall_1` (MANDATORY DIRECT ACCESS; cannot pass through another room)
- `bathroom_1` $\rightarrow$ `hall_1` OR `bedroom_1` (legal attached or common)
- `bathroom_2` $\rightarrow$ `hall_1` OR `bedroom_2` (legal attached or common)
- `pooja_1` $\rightarrow$ `hall_1` OR `kitchen_1` (legal direct access)

### Analysis of Access Deficit
1. **Total Linear Hall Boundary Required**:
   - `bedroom_1`: min width $10.0\text{ ft}$
   - `bedroom_2`: min width $10.0\text{ ft}$
   - `kitchen_1`: min width $8.0\text{ ft}$
   - Sum of minimum room widths requiring direct Hall contact: **$28.0\text{ ft}$ of unblocked, contiguous Hall interior edges**.
2. **Total Usable Hall Interior Edge Available**:
   - Under baseline ($14\times 16$): Only the North edge ($14.0\text{ ft}$) is usable. Available = $14.0\text{ ft}$. Deficit = **$14.0\text{ ft}$**.
   - Under Variant 7 ($10\times 22$): North edge ($10.0\text{ ft}$) + West edge past parking ($7.0\text{ ft}$) = $17.0\text{ ft}$. Deficit = **$11.0\text{ ft}$**.
3. **Can rooms act as passages?**
   - Bedrooms: **NO**. Passing through a bedroom to reach another room violates privacy rules (`INVALID_PASSAGE`).
   - Kitchen: **NO**. Passing through kitchen to reach bedrooms or bathrooms is prohibited.
   - Bathrooms: **NO**.
4. **Conclusion**:
   Three major rooms (`bedroom_1`, `bedroom_2`, `kitchen_1`) require direct Hall contact. The Hall on a 25 ft frontage can expose at most 10–14 ft on its North side, plus at most 5–7 ft along its side if elongated. It is geometrically impossible for 28 ft of room footprints to directly contact 14–17 ft of Hall perimeter.

---

## 10. Entrance Analysis

Verification of the 10 hard entrance invariants for all Hall variants:

1. **Entrance lies on plot boundary**: PASS (all variants anchored at $y = 0$, the South plot boundary).
2. **Entrance lies on Hall boundary**: PASS (Hall South edge is collinear with $y = 0$).
3. **Entrance side matches facing direction**: PASS (South side).
4. **Entrance has valid width**: PASS (standard $3.0\text{ ft}$ entrance door fits easily on $10\text{--}14\text{ ft}$ frontage).
5. **Entrance opens directly into Hall**: PASS (no intermediate foyer or space).
6. **No kitchen between entrance and Hall**: PASS.
7. **No bedroom between entrance and Hall**: PASS.
8. **No bathroom between entrance and Hall**: PASS.
9. **No pooja room between entrance and Hall**: PASS.
10. **Parking is not used as the main entrance**: PASS (main entrance door is placed independently on Hall frontage).

**Crucial Finding**:
The entrance constraint itself is 100% satisfied by the Hall variants. However, the requirement that the main entrance must open directly into `hall_1` from the exterior frontage forces `hall_1` to sit on the South boundary ($y = 0$). This front-anchoring traps the Hall between the exterior plot boundary, the side plot boundary, and the parking bay, starving it of interior perimeter.

---

## 11. Parking Interaction

- **Parking dimensions**: $10.0\text{ ft wide} \times 14.0\text{--}15.0\text{ ft deep}$.
- **Frontage consumption**: Parking consumes $10.0\text{ ft}$ of the $25.0\text{ ft}$ plot width ($40\%$).
- **Hall frontage consumption**: Hall consumes $14.0\text{ ft}$ ($56\%$).
- **Remaining frontage buffer**: $1.0\text{ ft}$ ($4\%$).
- **Impact on Hall interior accessibility**:
  Parking flanks the Hall along its entire depth for baseline variants ($y = 0..15$). Because parking is a utility space that cannot provide residential circulation or passage, the entire shared Hall-Parking wall ($14\text{--}15\text{ ft}$) is completely dead for room access.
- **Is Parking or Hall Geometry dominant?**
  They act in direct compounding synergy:
  The narrow 25 ft lot forces Parking and Hall to be side-by-side on the road frontage. This leaves Hall with only one open face (the North face), making room placement starved regardless of how Hall is resized.

---

## 12. Bottleneck Classification

The dominant failure classification is:
> **CONCLUSION D: Multiple constraints interact and no single bottleneck dominates.**
> Specifically: **Lot Width (25 ft) + Parking Frontage (10 ft) + Mandatory Direct Exterior Entrance to Hall + Mandatory Direct Hall Access for All Bedrooms/Kitchen** forms a closed overconstrained system.

### Detailed Constraint Interaction Chain
1. **Plot Width Constraint**: Total width is 25 ft.
2. **Exterior Entrance Constraint**: Main entrance must open directly from exterior frontage into `hall_1`.
3. **Vehicle Gate Constraint**: Parking must open directly to frontage.
4. **Frontage Division**: Road width (25 ft) = Parking (10 ft) + Hall (14 ft) + buffer (1 ft). Hall cannot be placed in the interior of the house because it must receive the exterior main entrance.
5. **Boundary Trapping**: Hall is anchored at frontage ($y=0$) and plot side line ($x=25$). Two faces of Hall are exterior boundaries. One face is blocked by parking.
6. **Access Choke**: Hall has only ONE interior face (North, 10–14 ft wide).
7. **Room Access Requirements**: 2 Bedrooms + 1 Kitchen require at least 28–30 ft of direct Hall contact.
8. **Result**: 0 complete candidates. Modifying Hall width, depth, or aspect ratio does NOT resolve this choke.

---

## 13. Comparison With Valid Cases

Why do other cases succeed while 25x40 South fails?

1. **Case C (25x40 West - VALID)**:
   - Frontage is on the West side ($40.0\text{ ft}$ depth dimension!).
   - On a 40 ft frontage, Parking (14 ft) and Hall (16 ft) leave $10.0\text{ ft}$ of open frontage.
   - Hall has $34.0\text{ ft}$ of interior edge, allowing Bed 1, Bed 2, and Kitchen to attach along East and North edges without contention.
2. **Case B (30x50 South - VALID in Root B)**:
   - Frontage is $30.0\text{ ft}$ ($5\text{ ft}$ wider than 25 ft).
   - Hall is $20.0\text{ ft}$ wide, providing $24.0\text{ ft}$ of interior edge.
   - The extra 5 ft plot width and 10 ft depth allows Root B to distribute rooms along the interior boundary without choking.
3. **Case D (40x50 East) & TC2 (VALID)**:
   - 40 ft frontage allows Hall to expose $46.0\text{ ft}$ of interior edge. All rooms easily attach.

**Key Insight**:
It is NOT that 25x40 is inherently too small in square footage ($1000\text{ sq ft}$ is ample for a 2BHK); it is that **South-facing orientation has its road on the narrow 25 ft dimension**, and the current architectural constraints require both Parking and Hall to touch this narrow frontage while requiring all habitable rooms to touch Hall directly.

---

## 14. Evidence

1. **Controlled Hall Geometry Test (Section 8)**:
   Tested 8 distinct Hall geometries (widths from 10 ft to 15 ft, depths from 14 ft to 22 ft, areas from 196 to 264 sq ft) across both Root A and Root B on 25x40 South.
   - Complete candidates generated: **0 across all variants**.
   - Valid layouts produced: **0 across all variants**.
   - Changing Hall geometry failed to produce even a single complete candidate.
2. **Step-by-Step Beam Search Failure Logging**:
   - In Variants 0–6 and 7b: `bedroom_1` generated 14 states, and `bedroom_2` generated **0 states** (`HALL_ACCESS` failure).
   - In Variant 7 ($10\times 22$): Elongating Hall past parking allowed `bedroom_2` to place (12 states), but then `kitchen_1` generated **0 states** (`HALL_ACCESS` failure).
   - When placing Kitchen first: Kitchen placed (4 states), `bedroom_1` placed (12 states), and `bedroom_2` generated **0 states**.
3. **Mathematical Proof of Usable Interior Edge**:
   - Hall requires $\ge 28\text{ ft}$ of direct contact for Bed 1 + Bed 2 + Kitchen.
   - Max possible interior edge on 25x40 South with frontage Hall is $17\text{ ft}$.
   - Deficit $\ge 11\text{ ft}$ is invariant to Hall aspect ratio.

---

## 15. Conclusion

**Hall geometry/aspect-ratio adaptation is NOT the primary bottleneck for the 25x40 South case.**

The hypothesis that "adjusting Hall aspect ratio will solve 25x40 South" is **refuted by empirical measurement and mathematical proof**:
- Testing 8 different Hall aspect ratios produced **0 valid layouts and 0 complete candidates**.
- The true root cause is a **compound architectural topology choke**: on narrow-frontage plots ($25\text{ ft}$), placing both Parking ($10\text{ ft}$) and Hall ($10\text{--}14\text{ ft}$) along the road edge while forbidding any circulation except direct Hall contact makes it physically impossible to connect two bedrooms and a kitchen directly to the Hall.

---

## 16. Recommendation for Phase 4D

In accordance with Section 20 of the Phase 4C specification:

### **SELECTED DECISION: OPTION C**
> **"Hall geometry contributes, but root topology/circulation/parking must be investigated further."**

### Rationale
1. Hall geometry adaptation alone does not produce valid layouts for 25x40 South (0 complete candidates across 8 variants).
2. Implementing adaptive Hall sizing in Phase 4D without addressing the circulation/root topology constraints will fail to rescue 25x40 South.
3. To solve narrow-frontage cases like 25x40 South in future phases, the system must investigate:
   - **T-shaped / L-shaped circulation or passage distribution** (allowing rooms to connect via an internal circulation node rather than requiring direct physical adjacency to Hall's perimeter), OR
   - **Alternative Root Topologies**: e.g., Tandem/Offset parking or an interior Hall layout with a defined entry foyer, OR
   - **Architectural Room Graph Flexibility**: Allowing secondary private rooms (e.g., Pooja or secondary Bathrooms) or nested access where appropriate.
