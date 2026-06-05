# Land Game — Game Design Document

> *Idea conceived 2018. Development started May 2026.*

---

## Vision

Land Game is a turn-based medieval economic strategy game set in loosely 14th-century Europe, inspired by Dutch/Flemish marshland colonization and drainage history. Players compete for economic dominance on a procedurally generated map. Land is acquired, developed, and traded. Trade goods flow between tiles. Financial instruments, mercenary contracts, and urban development all serve a single win condition: **highest total asset value**, reached either by turn limit or value threshold.

The game sits at the intersection of:
- **Monopoly** — land acquisition, property development, rent extraction, player elimination
- **Civilization** — tile-based map, terrain variety, sequential development ladder
- **EU4 / Victoria 3** — deep economic simulation, trade flows, financial instruments, market dynamics

This is a game that rewards the spreadsheet-brained player: every tile, contract, and futures position has a calculable expected value. But the emergent interactions — another player cornering your food supply, a plague event collapsing your city, a condottieri fleet breaking your trade routes — ensure the optimal play is never obvious.

---

## Win Condition

**Highest total asset value** at the end of the game. Asset value encompasses:

- Land holdings (by current valuation model)
- Buildings and improvements on owned tiles
- Liquid capital (gold/coin reserves)
- Financial instruments held (bonds, futures, swaps)
- Contracted trade flows (present value of expected future income)

Two end-game triggers:
1. **Turn limit** — game ends after N turns (configurable); player with highest total asset value wins
2. **Value threshold** — first player to reach a target total asset value wins outright

Bankruptcy ends a player's participation. A player unable to service debts or meet obligations is eliminated.

---

## Core Game Loop

Each turn, a player:

1. **Rolls** a d8 and moves across the map (terrain movement costs apply)
2. **Acts** on their current tile:
   - Purchase unowned land
   - Develop owned land (if eligible)
   - Interact with buildings (yours or rivals')
   - Execute market transactions (buy/sell trade goods, manage financial instruments)
   - Issue condottieri contracts or naval orders
3. **Collects** income from owned tiles, trade routes, and financial positions
4. **Resolves** event engine effects (if triggered this turn)

---

## Starting Conditions

### Modes

**Dispersed (default, Civ-style)**
- Map divided into player-count zones
- Each player spawns on the best-scoring tile within their zone
- Best-scoring = terrain variety + developable land + proximity to coast or river
- Minimum 15-tile separation between players

**Convergent (optional, Monopoly-style)**
- All players begin on the same central tile
- Early competition for nearby land is immediate

### Invalid Starting Terrains
Ocean, Mountain, Thick Forest, Cliff Coast, River (any tile with no development path).

---

## Turn Structure

**Sequential** (default) — players take full turns one at a time. This preserves the interaction model where visiting another player's tile is a deliberate act.

**Simultaneous** — under consideration for multiplayer to reduce downtime; requires resolving order-of-operations conflicts in the economic simulation.

---

## Map

- **Default size**: 60×40 (2,400 tiles) — roughly Netherlands scale
- **Large**: 80×50
- Square tile grid (not hexagonal)
- North = top, South = bottom; latitude affects terrain generation biases

### Why Square Tiles?

The natural matrix (row, col) indexing is central to the game's simulation: noise generation, spillover calculations, trade routing, and adjacency checks are all array operations. Hex grids require offset coordinate systems (axial or cube coords) that add abstraction everywhere. The movement mechanic is a die-roll — nobody is optimizing diagonal pathing. Economic and development systems are the game's substance, and they live in numpy matrices.

---

## Fog of War

Initial map is hidden. Tiles are revealed by movement through them. Outpost improvements extend vision radius. Naval vessels enable fog-of-war removal over water and coastal regions. *Exact fog mechanics TBD during prototyping.*

---

## UI & Map Modes

EU4-style multiple map view modes, switchable via keyboard:

| Mode | Display |
|---|---|
| **Terrain** | Color by terrain type |
| **Political** | Color by owner |
| **Value** | Heatmap by land_value, building_value, total_value (each toggle-able)|
| **Hydrology** | Highlights rivers, water terrain, coastal tiles |
| **Trade** | Trade flow routes and volumes |
| **Investment** | Development activity, improvement presence |

Map mode colors are computed at render time as a pure function of `(tile, map_mode)`. They are never stored on the tile.

---

## Open Design Questions

- Turn structure: simultaneous vs sequential (final decision)
- Fog of war reveal mechanics (radius, outpost range)
- Exact building slot rules and upgrade conditions
- Soil exhaustion / land health mechanic
- Victory condition tuning (turn limit N, value threshold T)
- Whether influence decays differently across terrain types
- Influence parameter: single scalar vs vector
- Financial instrument physical collectible variant (token on map vs menu interaction)

---

*See also: `02_terrain_system.md`, `03_economic_systems.md`, `04_algorithms.md`, `05_architecture.md`*
