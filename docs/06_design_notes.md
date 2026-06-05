# Design Notes & Open Questions

This document captures design decisions that were deferred, ideas under consideration, and open questions to resolve during prototyping. It is a living document — items should be moved to the appropriate spec document once resolved.

---

## Resolved Decisions (for reference)

These were actively debated and resolved:

**Square tiles vs hex tiles** → **Square tiles**
Rationale: natural matrix indexing for numpy; movement mechanic is a die roll, not tactical maneuvering; economic simulation benefits outweigh hex movement uniformity.

**Hills as standalone terrain vs continuous scalar** → **Continuous scalar (`hills_scalar` 0.0 → 1.0)**
Rationale: avoids explosion of terrain enum variants; enables smooth compositional terrain; the validity matrix blocks physically impossible combinations without hard-coding a large enum.

**Marsh + hills combination** → **Invalid (blocked by validity matrix)**
Real-world constraint: marshland is by definition low-lying and waterlogged; cannot co-exist with hilliness.

**AI diffuse vs specialist** → **Both are viable; diffuse is not inherently weaker**
A pure archetype AI is easy to counter. A diffuse AI is less predictable and may outperform in specific matchups despite lower average decision quality.

**Adjacency matrix orientation** → **Column-stochastic**
Columns represent the source terrain. Each column sums to 100. Rows carry no normalization constraint. The matrix is intentionally asymmetric.

**Renderer for prototype** → **pygame**
FastAPI is in the dependency list for a future Python backend + React frontend split, but pygame is the path to a first playable prototype.

---

## Open Design Questions

### Turn Structure

- **Sequential** (current default assumption) vs **Simultaneous**
- Sequential preserves the "visit another player's tile" interaction clearly
- Simultaneous reduces downtime in multiplayer but requires resolving simultaneous market actions
- *Decision: default to sequential; revisit for multiplayer*

### Fog of War

- Exact reveal radius for outpost improvements (TBD)
- Whether naval vessels have a different reveal mechanic (larger radius, water tiles)
- Starting reveal: do players start with their starting zone partially revealed?

### Building Slot Rules

- Exact conditions for upgrading buildings to tier 2 and tier 3 (beyond population gating)
- Whether a tile can have two buildings of the same type (probably not)
- Whether buildings can be demolished and what the gold penalty is

### Soil Exhaustion / Land Health

- Considered but not specified: intensive farming could degrade output over time
- Would require a `soil_health` scalar on agricultural tiles
- Interacts with the famine/structural decline pathway
- *Status: promising but deferred to prototyping phase*

### Victory Condition Tuning

- Turn limit N: what value makes for a satisfying game length?
- Value threshold T: what value is aspirational but achievable?
- Should the turn limit be visible to all players (clock pressure)?
- Multiple win conditions simultaneously active vs one or the other per game config?

### Influence Parameter

- Land valuation spillover: single scalar `spillover_radius` vs a full influence vector (directional, or terrain-weighted)
- A directional influence vector (e.g. spillover stronger along roads, weaker across mountains) would be more realistic but significantly more complex
- *Status: start with isotropic inverse-square; consider directional in a later pass*

### Population Caps

- Is there a hard population cap per metro, or just a soft ceiling via resource constraints?
- Hard cap: simpler, prevents runaway scaling
- Soft cap (resource-constrained): more realistic, more interesting strategic decisions

### Financial Instruments as Physical Tokens

- Optional variant: futures and bonds appear as collectible tokens on the map
- Players must physically move to acquire them
- Adds spatial dimension to financial play; may feel gimmicky
- *Status: optional variant, implement after core financial layer is working*

### Condottieri Reliability

- Exact reliability risk mechanic: flat probability per turn? Escalating with contract length? Modified by price paid?
- What does "underperformance" mean mechanically: mission fails entirely, partial effectiveness, or delayed?

### World Age Effect on Hills Scalar Weights

- Young world: higher β weight (Sobel/elevation-driven ruggedness) → sharper, more dramatic terrain
- Old world: higher γ weight (neighbour influence) → smoother, more gradual hills
- Exact weight shift values TBD

### Map Fragmentation Setting

- How exactly does fragmentation affect the adjacency matrix scaling?
- High fragmentation = lower multipliers on same-type adjacency (terrains don't cluster as strongly) + higher multipliers on cross-type adjacency
- Low fragmentation = opposite: biomes are large and cohesive
- Implementation: a single `fragmentation` scalar that linearly interpolates between two pre-defined multiplier tables

### Trade Route Conflict Resolution

- If two players want to route goods through the same tile corridor, is there a capacity limit?
- Does a blockade affect all traffic or can be targeted?

---

## Deferred Ideas (Good But Not Now)

These were raised and accepted in principle but explicitly deferred:

**Bridges as improvements**
Roads and canals are milestone 1 improvements. Bridges are a later addition — they add complexity to the water crossing mechanic and require clear river tile rules first.

**Soil exhaustion**
Promising mechanic (intensive farming degrades output; incentivizes crop rotation or fallow periods) but adds a `soil_health` field to tiles and a new simulation loop. Deferred until the base farming system is working.

**Influence vector (directional spillover)**
The isotropic inverse-square spillover is the baseline. A directional influence vector (roads amplify spillover; mountains reduce it) would be a significant depth addition in a later pass.

**Casino minigame**
The Tavern building enables a gambling mechanic. Specifics not designed — left as a fun polish-phase problem.

**Named condottieri historical flavor**
The condottieri market features named historical mercenary companies ("3rd Fleet of Genoa", etc.) with distinct characteristics. The flavor and capability table is a design-and-data task, not a code problem. Deferred to content pass.

**Steam release specifics**
Distribution via Steam is the target but the specific packaging (PyInstaller, cx_Freeze, etc.) and store page requirements are a shipping concern, not a design concern. Deferred.

---

## Implementation Gotchas

Things that have been explicitly discussed and should not be re-litigated:

- **No notebooks**: pure Python scripts and config files only. No Jupyter notebooks in the repo.
- **Setup script is structure-only**: `setup_project.py` creates directories and files but contains no stub implementations.
- **Elevation demoted after rivers**: rivers must be extracted from the Perlin heightmap *before* elevation becomes just a bias scalar. This ordering is load-bearing.
- **Adjacency matrix is column-only**: do not attempt to normalize rows. Only columns have meaning. Row sums are irrelevant.
- **Render colors are never stored on tiles**: all rgba values are computed at render time per map mode. Adding stored color fields to Tile is a design error.
- **Land value is dirty-flagged**: do not compute land value eagerly on every tile update. The dirty flag exists precisely to avoid O(N×M) recomputation on every action.
