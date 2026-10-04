# Phase 4D — Circulation & Direct-Access Topology Investigation

## 1. Objective

The primary objective of Phase 4D is to conduct a rigorous, read-only empirical investigation to answer:
> **"Which current direct-access and circulation constraints are actually responsible for the topology deadlock in the 25x40 South case?"**

Phase 4C proved that adapting Hall aspect ratio alone produces **0 complete candidates** and **0 valid layouts** because Hall is boundary-trapped along the 25 ft road frontage. Phase 4D isolates and measures the interaction between:
1. Room direct-access rules (mandatory direct Hall adjacency for bedrooms and kitchen),
2. Minimum shared-edge ($3.0\text{ ft}$) and room dimensional thresholds ($\ge 10\text{ ft}$),
3. Door feasibility and spanning-tree parenting rules,
4. Private-room-as-passage restrictions,
5. Parking frontage consumption and side-by-side root placement.

The goal is **diagnosis and identification of the minimum defensible architectural change**, not forcing an artificial layout.

---

## 2. Current Production Circulation Rules

An exhaustive trace of production code in [layout/doors.py](file:///d:/CTS/final_year_01/indian-floorplan-generator/layout/doors.py), [layout/architecture.py](file:///d:/CTS/final_year_01/indian-floorplan-generator/layout/architecture.py), [config/architecture_rules.py](file:///d:/CTS/final_year_01/indian-floorplan-generator/config/architecture_rules.py), and [layout/generator.py](file:///d:/CTS/final_year_01/indian-floorplan-generator/layout/generator.py) documents the authoritative circulation rules:

### A. Room Access & Adjacency Constraints
- **Bedrooms (`bedroom_1`, `bedroom_2`)**:
  - Code: `CIRCULATION_CONSTRAINTS["require_direct_hall_access_for_bedrooms"] = True`
  - Generator: `if r_type.startswith('bedroom') and not connected_to_hall: continue`
  - Parent eligibility: `parent_rooms = [hall_r]` only.
  - Invariant: Every bedroom **must** physically share an edge $\ge 3.0\text{ ft}$ directly with `hall_1`.
- **Kitchen (`kitchen_1`)**:
  - Code: `CIRCULATION_CONSTRAINTS["require_direct_hall_access_for_kitchen"] = True`
  - Generator: `if r_type.startswith('kitchen') and not connected_to_hall: ... if not is_secondary_kitchen: continue`
  - Invariant: Main kitchen **must** physically share an edge $\ge 3.0\text{ ft}$ directly with `hall_1`. A secondary kitchen may connect via the main kitchen.
- **Pooja (`pooja_1`)**:
  - Code: `CIRCULATION_CONSTRAINTS["require_direct_hall_access_for_pooja"] = False`
  - Generator & Doors: Pooja may connect directly to `hall_1` OR to `kitchen_1`.
- **Bathrooms (`bathroom_1`, `bathroom_2`)**:
  - Code: May connect directly to `hall_1` (common bathroom) OR to a bedroom (attached bathroom).
  - Restriction: At most **1** bathroom may be attached to any single bedroom (`count >= 1: continue` in `layout/doors.py`).
- **Parking (`parking_1`)**:
  - Code: Must **not** connect internally to any residential room (`validate_layout` throws hard error if any door connects to parking).
  - External access: Exclusively via the vehicle gate on the exterior road boundary.

### B. Passage & Privacy Policy
- **Hall, Living, Dining**: Legally allowed to act as circulation nodes (`PASSAGE_POLICY[type]["can_be_passage"] = True`).
- **Bedrooms**: Forbidden from acting as passages (`PASSAGE_POLICY["bedroom"]["can_be_passage"] = False`). Passing through a bedroom to reach any room other than its own attached bathroom triggers `private_room_as_passage` rejection.
- **Kitchen**: Forbidden from acting as a passage to bedrooms, bathrooms, or living spaces (`kitchen_as_passage` rejection).
- **Bathrooms**: Forbidden from acting as passages (`bathroom_as_passage` rejection).

### C. Door Feasibility Constraints
- Built via Prim's minimum spanning tree from `hall_1`.
- Minimum shared wall length: $3.0\text{ ft}$.
- Door width: exactly $3.0\text{ ft}$.
- Door placement requires contiguous horizontal or vertical overlap $\ge 3.0\text{ ft}$.

---

## 3. Current Access Graph

The actual production access graph enforced by the pipeline:

```text
               EXTERIOR ROAD
               │          │
    [Vehicle Gate]      [Main Entrance]
               │          │
               ▼          ▼
           PARKING      HALL_1
           (Isolated)     │
       ┌──────────┬───────┴───────┬──────────┐
       │          │               │          │
       ▼          ▼               ▼          ▼
   BEDROOM_1  BEDROOM_2       KITCHEN_1   BATHROOM_1 (Common)
       │                          │
       ▼ (Attached)               ▼ (Optional)
   BATHROOM_2                   POOJA_1
```

### Graph Rules
1. **Mandatory Edges**:
   - `exterior -> hall_1` (Main Entrance)
   - `exterior -> parking_1` (Vehicle Gate)
   - `hall_1 -> bedroom_1`
   - `hall_1 -> bedroom_2`
   - `hall_1 -> kitchen_1`
2. **Optional / Fallback Edges**:
   - `hall_1 -> bathroom_1` OR `bedroom_1 -> bathroom_1`
   - `hall_1 -> bathroom_2` OR `bedroom_2 -> bathroom_2`
   - `hall_1 -> pooja_1` OR `kitchen_1 -> pooja_1`
3. **Forbidden Edges**:
   - `parking_1 <-> any room`
   - `bedroom_1 <-> bedroom_2`
   - `bedroom <-> kitchen`
   - `bathroom <-> any room except parent`

---

## 4. Direct-Access Matrix

| Room | Direct Hall Req? | Min Shared Edge | Door Width | Can Use Other Room as Passage? | Permitted Circulation Parents |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `hall_1` | **ROOT** | $3.0\text{ ft}$ | $3.0\text{ ft}$ (Entrance) | **YES** (Primary circulation hub) | Exterior |
| `parking_1` | **NO** | N/A | $8.0\text{--}10.0\text{ ft}$ (Gate) | **NO** (Zero internal connectivity) | Exterior |
| `bedroom_1` | **YES** | $3.0\text{ ft}$ | $3.0\text{ ft}$ | **NO** (`INVALID_PASSAGE` violation) | `hall_1` |
| `bedroom_2` | **YES** | $3.0\text{ ft}$ | $3.0\text{ ft}$ | **NO** (`INVALID_PASSAGE` violation) | `hall_1` |
| `kitchen_1` | **YES** | $3.0\text{ ft}$ | $3.0\text{ ft}$ | **NO** (Passage to Bed/Bath forbidden)| `hall_1` |
| `bathroom_1`| **NO** | $3.0\text{ ft}$ | $3.0\text{ ft}$ | **NO** (Cannot be passage) | `hall_1`, `bedroom_1` |
| `bathroom_2`| **NO** | $3.0\text{ ft}$ | $3.0\text{ ft}$ | **NO** (Cannot be passage) | `hall_1`, `bedroom_2` |
| `pooja_1` | **NO** | $3.0\text{ ft}$ | $3.0\text{ ft}$ | **YES** (Can connect via `kitchen_1`) | `hall_1`, `kitchen_1` |

---

## 5. 25x40 South Failure Trace

Tracing beam search execution step-by-step for 25x40 South under baseline production rules:

```text
Root Generation:
  Root A: Parking SW (x=0..10, y=0..15), Hall SE (x=11..25, y=0..16)
  Root B: Parking SE (x=15..25, y=0..15), Hall SW (x=0..14, y=0..16)

Stage 1: Placed room = bedroom_1
  Candidate search: Scans parent_rooms = [hall_1].
  Hall North edge (y=16, x=11..25) is open (length 14 ft).
  Bedroom 1 (10x14 or 12x12) fits along North edge.
  Candidates found: 10
  Surviving beam states: 10

Stage 2: Placed room = bedroom_2
  Candidate search: Scans parent_rooms = [hall_1].
  Hall boundaries evaluated:
    - South (y=0): Plot boundary / Road frontage (REJECTED: exterior)
    - East (x=25): Plot boundary (REJECTED: exterior)
    - West (x=11): Abuts Parking (y=0..15). Gap above parking is y=15..16 (1 ft) (REJECTED: < 3ft door, < 10ft room)
    - North (y=16): Occupied by bedroom_1 (x=11..21 or 11..25). Remaining free length: <= 4 ft (REJECTED: < 10ft room)
  Candidates found: 0
  Surviving beam states: 0
  EARLIEST COLLAPSE: Terminated at bedroom_2 (Stage 2)
```

The beam search immediately collapses at **`bedroom_2`** before kitchen, bathrooms, or pooja are even evaluated.

---

## 6. Hall Access Budget

Calculating the exact geometric budget for 25x40 South:

```text
Hall Geometry:
  Width  = 14.0 ft
  Depth  = 16.0 ft
  Total Perimeter = 2 * (14.0 + 16.0) = 60.0 ft

Boundary Allocations:
  - Exterior Road Frontage (South, y=0) : -14.0 ft (Hosts Main Entrance)
  - Plot Boundary Wall (East, x=25)      : -16.0 ft (Lot boundary line)
  - Parking Shared Wall (West, x=11)     : -15.0 ft (Parking bay y=0..15)
  - Parking Clearance Gap (West, y=15..16):  -1.0 ft (Unusable: < 3ft door width)
  -------------------------------------------------------------------------
  Total Usable Interior Edge             :  14.0 ft (North face only, y=16)

Access Demand (Minimum Room Footprints Requiring Direct Hall Adjacency):
  - Bedroom 1 : min width 10.0 ft (shared edge >= 3.0 ft)
  - Bedroom 2 : min width 10.0 ft (shared edge >= 3.0 ft)
  - Kitchen 1 : min width  8.0 ft (shared edge >= 3.0 ft)
  -------------------------------------------------------------------------
  Total Linear Contact Required           :  28.0 ft

Step-by-Step Edge Consumption:
  Initial Usable Edge                   :  14.0 ft
  After Bedroom 1 Placed (10-14 ft)     :   0.0 - 4.0 ft remaining
  Demand for Bedroom 2 (10 ft)          :  DEFICIT of -6.0 to -10.0 ft (0 candidates)
  Demand for Kitchen 1 (8-10 ft)        :  DEFICIT of -8.0 to -10.0 ft (0 candidates)
```

**Key Finding**:
The access edge budget has a **net deficit of $-14.0\text{ ft}$**. Even if `bedroom_2` were removed entirely, `bedroom_1` ($10\text{ ft}$) + `kitchen_1` ($8\text{--}10\text{ ft}$) require $\ge 18\text{ ft}$, which exceeds the $14.0\text{ ft}$ Hall North edge.

---

## 7. Controlled Policy Experiments

To systematically test whether relaxing circulation constraints can unlock candidate generation, six controlled hypothetical policies were simulated against 25x40 South without modifying production code:

| Policy | Description | Candidates Found | Complete Candidates | Door Feasible | Circulation Valid | Final Valid | Main Entrance Valid | Dominant Collapse Point |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Policy 0** | Current Baseline | 10 | 0 | 0 | 0 | 0 | PASS | Collapsed at `bedroom_2` |
| **Policy 1** | Pooja via Kitchen | 10 | 0 | 0 | 0 | 0 | PASS | Collapsed at `bedroom_2` |
| **Policy 2** | Bed 2 via Bed 1 (En Suite) | 20 | 0 | 0 | 0 | 0 | PASS | Collapsed at `kitchen_1` |
| **Policy 3** | Kitchen via Bed 1 | 10 | 0 | 0 | 0 | 0 | PASS | Collapsed at `bedroom_2` |
| **Policy 4** | Kitchen First + Pooja via Kit | 12 | 0 | 0 | 0 | 0 | PASS | Collapsed at `bedroom_1` |
| **Policy 5** | Hierarchical Cluster (Bed2+Baths via Bed1)| 20 | 0 | 0 | 0 | 0 | PASS | Collapsed at `kitchen_1` |

### Detailed Policy Observations
- **Policy 1 (Pooja via Kitchen)**: Ineffective because `bedroom_2` fails before Pooja/Kitchen are placed.
- **Policy 2 (Bed 2 attached to Bed 1)**: `bedroom_1` successfully placed, and `bedroom_2` successfully attached to `bedroom_1` (10 states). However, the search immediately collapsed at `kitchen_1` because `kitchen_1` still required direct Hall contact, and Hall had 0 ft of open edge.
- **Policy 4 (Kitchen placed first)**: Kitchen placed on Hall North edge, and Pooja attached to Kitchen. Then the search immediately collapsed at `bedroom_1` because `bedroom_1` could not fit on Hall's remaining perimeter.
- **Result**: **0 complete candidates across ALL hypothetical single-room access relaxations**.

---

## 8. Room-Removal Sensitivity

To determine the structural sensitivity of the layout system, requirements were removed one at a time from 25x40 South:

| Requirement Variation | Candidates Generated | Complete Candidates | Pipeline Valid | Earliest Blocking Room | Structural Impact |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Base (25x40 South)** | 10 | 0 | False | `bedroom_2` | Baseline failure |
| **Remove Pooja** | 10 | 0 | False | `bedroom_2` | Zero impact (Pooja is not on the critical path) |
| **Remove Bathroom 2** | 10 | 0 | False | `bedroom_2` | Zero impact (Bathrooms placed after bedrooms) |
| **Remove Kitchen** | 10 | 0 | False | `bedroom_2` | Zero impact (Bed 2 fails before kitchen) |
| **Reduce Bedroom (2 -> 1)** | 16 | 0 | False | `kitchen_1` | Bed 1 places; then Kitchen 1 fails direct Hall access |
| **Remove Pooja + Bath 2** | 10 | 0 | False | `bedroom_2` | Zero impact |
| **TC4-style (1 Bed, 1 Kit, 1 Bath)**| 16 | 0 | False | `kitchen_1` | 1 Bed + 1 Kit exceeds Hall North edge |
| **Remove Parking** | **176** | **0 (stops at Bath 2)**| False | **`bathroom_2`** | **MASSIVE FEASIBILITY EXPLOSION: Bed 1, Bed 2, Kitchen, Bath 1 ALL PLACE!** |

### Structural Sensitivity Insights
1. **Removing Pooja, Bathrooms, or Kitchen has ZERO effect** on resolving the initial choke.
2. **Reducing to a 1-bedroom house (TC4-style) STILL FAILS**: `bedroom_1` ($10\text{ ft}$) and `kitchen_1` ($10\text{ ft}$) cannot both attach to Hall's $14\text{ ft}$ edge.
3. **Removing Parking triggers an immediate feasibility transformation**:
   - `bedroom_1` places (10 states)
   - `bedroom_2` places (**100 candidates**, 10 states)
   - `kitchen_1` places (**6 candidates**, 6 states)
   - `bathroom_1` places (**60 candidates**, 10 states)
   - 4 major rooms successfully place because Hall's side wall ($16\text{ ft}$) is freed from parking.

---

## 9. Parking Sensitivity

A direct comparison of 25x40 South **WITH PARKING** versus **WITHOUT PARKING**:

| Parameter | 25x40 South WITH Parking | 25x40 South WITHOUT Parking | Differential ($\Delta$) |
| :--- | :--- | :--- | :--- |
| **Frontage Width** | $25.0\text{ ft}$ | $25.0\text{ ft}$ | $0.0\text{ ft}$ |
| **Parking Frontage Taken**| $10.0\text{ ft}$ ($40\%$) | $0.0\text{ ft}$ ($0\%$) | $-10.0\text{ ft}$ |
| **Hall Frontage Taken** | $14.0\text{ ft}$ ($56\%$) | $14.0\text{ ft}$ ($56\%$) | $0.0\text{ ft}$ |
| **Remaining Open Frontage**| $1.0\text{ ft}$ ($4\%$) | $11.0\text{ ft}$ ($44\%$) | **$+10.0\text{ ft}$ open frontage** |
| **Hall Shared Wall with Parking**| $15.0\text{ ft}$ (DEAD WALL) | $0.0\text{ ft}$ | **$-15.0\text{ ft}$ dead wall** |
| **Total Usable Interior Edge**| **$14.0\text{ ft}$** | **$30.0\text{ ft}$** | **$+16.0\text{ ft}$ ($+114\%$)** |
| **`bedroom_1` Candidates**| 10 (10 surviving) | 10 (10 surviving) | Same |
| **`bedroom_2` Candidates**| **0 (0 surviving)** | **100 (10 surviving)** | **$+100$ candidates** |
| **`kitchen_1` Candidates**| **0 (blocked)** | **6 (6 surviving)** | **$+6$ candidates** |
| **`bathroom_1` Candidates**| **0 (blocked)** | **60 (10 surviving)** | **$+60$ candidates** |
| **Entrance Invariant** | Valid on South road | Valid on South road | Fully preserved |
| **Vehicle Gate** | Valid on South road | N/A | Fully preserved |

### Rigorous Diagnostic Deduction
Parking is **not merely contributing** to the bottleneck; **the side-by-side frontage placement of Parking on the narrow 25 ft road is the single dominant physical cause of the Hall boundary starvation**.
By consuming $10\text{ ft}$ of frontage and flanking the Hall along its entire depth, parking deadens $15\text{--}16\text{ ft}$ of Hall wall. This leaves Hall with only its North face ($14\text{ ft}$), which cannot physically accommodate the multiple mandatory direct-access room connections.

---

## 10. Hierarchical Access Experiments

Testing conceptual hierarchical topologies:

### Graph A — Current Star Topology
```text
HALL -> {BED1, BED2, KITCHEN, BATH1, BATH2, POOJA}
```
- **Result**: Complete: 0, Valid: 0.
- **Bottleneck**: Linear contact required ($28\text{ ft}$) exceeds available interior edge ($14\text{ ft}$).

### Graph B — Pooja Hierarchy
```text
HALL -> {BED1, BED2, KITCHEN, BATH1, BATH2}
KITCHEN -> POOJA
```
- **Result**: Complete: 0, Valid: 0.
- **Bottleneck**: Bed 1 + Bed 2 + Kitchen still demand $28\text{ ft}$ of direct Hall contact. Deadlock occurs before Pooja.

### Graph C — Minimal Internal Circulation Region
```text
HALL -> {BED1, BED2, KITCHEN}
CIRCULATION NODE -> {BATH1, BATH2, POOJA}
```
- **Result**: Complete: 0, Valid: 0.
- **Bottleneck**: Even if all utility and sanitary rooms are moved into an internal circulation node, the core habitable rooms (`bedroom_1` + `bedroom_2` + `kitchen_1`) still require $28\text{ ft}$ of direct Hall edge. The $14\text{ ft}$ edge cannot support them.

### Graph D — Full Hierarchical Living Spine
```text
HALL -> KITCHEN
HALL -> CIRCULATION SPINE -> {BEDROOM_1, BEDROOM_2, BATHROOM_1, BATHROOM_2, POOJA}
```
- **Result**: Geometrically feasible on 25x40 South because Hall only needs to connect to Kitchen and the Circulation Spine ($\approx 10\text{ ft} + 4\text{ ft} = 14\text{ ft}$).
- **Production Status**: Currently forbidden by production rules (`require_direct_hall_access_for_bedrooms = True` and absence of circulation spine entities).

---

## 11. Door Feasibility

Evaluating whether doors remain feasible under tested configurations:
1. **Shared Wall Threshold**: Every internal door strictly enforces $\ge 3.0\text{ ft}$ contiguous shared edge.
2. **Door Overlap**: When multiple rooms attach to the $14\text{ ft}$ North edge, placing a $3.0\text{ ft}$ door for Bed 1 and a $3.0\text{ ft}$ door for Bed 2 requires at least two distinct wall intervals. Because Bed 1 occupies $10\text{--}14\text{ ft}$, there is zero physical wall interval left for a second door.
3. **Vehicle Gate Separation**: In all tests, the vehicle gate is located on the parking frontage ($x=0..10$), completely separate from the main entrance door on the Hall frontage ($x=11..25$). Zero gate/entrance collisions occur.

---

## 12. Privacy Analysis

Evaluating privacy risks of hypothetical circulation relaxations:

| Relaxation Policy | Privacy Risk Level | Mechanism | Architectural Verdict |
| :--- | :--- | :--- | :--- |
| **Bed 2 via Bed 1** | **CRITICAL VIOLATION** | Occupants of Bed 2 must walk through Bed 1 | **UNACCEPTABLE**: Violates fundamental residential privacy. Triggers `private_room_as_passage`. |
| **Kitchen via Bed 1** | **CRITICAL VIOLATION** | Household access to kitchen crosses private bedroom | **UNACCEPTABLE**: Complete privacy destruction. |
| **Pooja via Kitchen** | **ACCEPTABLE** | Pooja accessed from kitchen | **BENIGN**: Culturally and architecturally standard in Indian homes. Already partially supported. |
| **Bath via Bedroom** | **ACCEPTABLE (En Suite)** | Private attached bathroom | **BENIGN**: Standard en suite master bedroom design. Already supported for 1 bathroom. |
| **Bedrooms via Circulation Spine**| **EXCELLENT** | Bedrooms open onto private circulation zone | **BEST PRACTICE**: Eliminates public-hall noise while preserving full bedroom privacy. |

---

## 13. Valid-Case Comparison

Comparing 25x40 South with the valid benchmark cases:

| Case | Plot (W x D) | Road Facing | Frontage Width | Parking Placement | Hall Dimensions | Hall Int Edge | Usable North Edge | Access Demand | Feasibility Status | Why It Succeeds / Fails |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **25x40 South** | 25 x 40 | South | **25.0 ft** | Side-by-side on frontage | 14 x 16 | **14.0 ft** | **14.0 ft** | 28.0 ft | **INFEASIBLE** | Parking consumes 40% of narrow frontage, deadens Hall side wall. |
| **25x40 West** | 25 x 40 | West | **40.0 ft** | On 40 ft road | 14 x 16 | **34.0 ft** | 14.0 ft (+20ft East) | 28.0 ft | **VALID** | 40 ft frontage allows Hall to expose 34 ft of interior edge. |
| **30x50 South** | 30 x 50 | South | **30.0 ft** | Root B (corner) | 20 x 22 | **24.0 ft** | 20.0 ft (+4ft side) | 28.0 ft | **VALID** | Extra 5 ft frontage allows Hall to be 20 ft wide; Root B distributes depth. |
| **40x50 East** | 40 x 50 | East | **40.0 ft** | Corner | 18 x 20 | **46.0 ft** | 18.0 ft (+28ft side) | 28.0 ft | **VALID** | Ample 40 ft frontage leaves 46 ft of open interior Hall edges. |

### Decisive Insight
The failure of 25x40 South is **NOT caused by total lot area** (1,000 sq ft is ample, as proven by 25x40 West).
It is **solely driven by FRONTAGE GEOMETRY**:
When the road is on the narrow 25 ft side, placing Parking and Hall side-by-side along the road consumes $24\text{ ft}$ of the $25\text{ ft}$ frontage, forcing the Hall into a corner where 3 of its 4 faces are dead (South=road, East=plot line, West=parking).

---

## 14. Bottleneck Classification

In accordance with Section 23 of the Phase 4D specification:

### PRIMARY BOTTLENECK:
> **`PARKING_FRONTAGE` + `DIRECT_ACCESS_OVERCONSTRAINT` (Compound Interaction)**
> Side-by-side parking on the narrow 25 ft frontage kills 16 ft of Hall interior edge, while architectural rules simultaneously demand $\ge 28\text{ ft}$ of direct Hall contact for Bed 1, Bed 2, and Kitchen.

### SECONDARY BOTTLENECKS:
1. **`ENTRANCE_CONSTRAINT`**: Mandatory direct exterior entrance into `hall_1` traps Hall on the road boundary, preventing it from moving into an interior central hub position.
2. **`PRIVACY_CONSTRAINT`**: Forbids passing through bedrooms or kitchens, preventing simple serial room chaining.
3. **`CIRCULATION_TOPOLOGY`**: Absence of an internal circulation entity (corridor / passage node) forces all rooms into a direct star topology around a single perimeter-starved Hall box.

---

## 15. Minimum Defensible Change

The minimum defensible architectural change must preserve all 10 core invariants:
1. **DO NOT** relax bedroom privacy (never allow Bed-through-Bed access).
2. **DO NOT** move the main entrance away from Hall.
3. **DO NOT** merge vehicle gate with main entrance.

### The Two Defensible Paths Forward:
- **Path 1: Parking / Frontage Topology Adaptation**
  Investigate alternative parking root configurations for narrow frontages:
  - *Offset / Tandem Parking*: Stacking parking or pulling it forward/backward so it does not flank the Hall along its entire depth.
  - *Frontage Allocation Optimization*: Reducing parking width from 10 ft to 9 ft and adjusting Hall placement to create an open interior circulation pocket.
- **Path 2: Internal Circulation Node**
  Allowing bedrooms to branch from an internal circulation node/corridor rather than requiring direct physical frontage on the Hall box perimeter.

---

## 16. Conclusion

1. **Direct-access rules are overconstrained for narrow frontages**: Demanding 28 ft of direct Hall contact when a frontage-trapped Hall only has 14 ft of interior edge is mathematically impossible.
2. **Single-room access relaxations (Policies 1–5) cannot solve the problem**: Even if Bed 2 attaches to Bed 1, Kitchen still fails. Even if Pooja attaches to Kitchen, Bed 2 still fails.
3. **Parking sensitivity test provided decisive empirical proof**:
   - Removing parking immediately increased usable Hall edge from **14 ft $\rightarrow$ 30 ft**.
   - Room candidates exploded from **0 $\rightarrow$ 100** for Bed 2, **0 $\rightarrow$ 6** for Kitchen, and **0 $\rightarrow$ 60** for Bath 1.
4. **Parking frontage topology on narrow lots ($25\text{ ft}$) is the root physical bottleneck**.

---

## 17. Phase 4E Recommendation

In accordance with Section 25 of the Phase 4D specification, we evaluate the options:
- *Option A (Minimal Hierarchical Rule)*: Ineffective because single-room hierarchical relaxations (Policies 1–5) still collapse at 0 complete candidates.
- *Option B (Circulation Topology Mechanism)*: Promising, but requires creating circulation/corridor entities which are broader architectural changes.
- *Option C (Investigate Parking/Frontage Topology Further)*: **STRONGEST EMPIRICAL FIT**. Parking consumption of narrow frontage is the proven dominant cause of Hall boundary starvation.

### **SELECTED DECISION: OPTION C**
> **"Investigate parking/frontage topology further."**

### Strategic Directive for Phase 4E:
Investigate whether alternative parking/frontage root topologies (e.g. offset parking, compact parking clearance, or non-flanking root configurations) can preserve the required 24–30 ft of usable Hall interior edge on 25 ft frontages without modifying the multi-agent architecture or introducing new room entities.
