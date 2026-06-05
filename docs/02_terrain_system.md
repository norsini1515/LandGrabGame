# Terrain System

---

## Terrain Types

The game has **14 base terrain types**. Hills and mountains are encoded as a continuous `hills_scalar` on the tile, not as independent terrain types. This enables compositional terrain (e.g. Forest + hills modifier) without an explosion of enum variants.

| Terrain | Base Movement Cost | Notes |
|---|---|---|
| Plains | 1 | Most developable; wheat and grain output |
| Grassland | 1 | Livestock, wool; slightly better for farming than plains |
| Forest | 2 | Lumber; clearable |
| Thick Forest | 3 | Hardwood; harder to clear; different dev tree than Forest |
| Jungle | 4 | Exotic goods; extremely difficult to develop |
| Marsh | 3 | Requires dredging; historically the core inspiration |
| Desert | 2 | Sparse output; specialized dev path |
| Deep Desert | 3 | Near-impassable; minimal development potential |
| Tundra | 3 | Cold biome; limited farming |
| Frozen Tundra | 4 | Extreme cold; near-impassable |
| Coastal | 1 | Land bordering ocean; enables ports |
| Floodplain | 2 | Fertile but flood-prone; coastal adjacent |
| Cliff Coast | 3 | Impassable coastline; no port eligibility |
| Mountain | 5 | Base movement cost; further modified by hills_scalar |

### Hills Scalar Thresholds

The `hills_scalar` is a continuous value 0.0 → 1.0 representing terrain ruggedness.

| Scalar Range | Classification |
|---|---|
| 0.0 → 0.20 | Flat — no hills modifier applied |
| 0.20 → 0.75 | Hills modifier applied to base terrain |
| 0.75 → 1.0 | Mountain (standalone or combined) |

Thresholds `hills_flat_threshold = 0.20` and `hills_mountain_threshold = 0.75` are tunable constants in `terrain.config`.

### Combined Terrain Cost Formula

When a hills modifier applies:

```
combined_cost = a + (b + c)
```

Where:
- `a` = base terrain cost
- `b` = hills modifier cost (treated as an additive penalty)
- `c` = tunable constant, **default -1** (softens the combined penalty)

This formula is intentionally asymmetric with the base costs — combining Forest (2) with hills feels different than combining Plains (1) with hills.

### Terrain Validity Constraints

A **14×3 validity matrix** blocks impossible terrain-elevation combinations. For example, Marsh cannot combine with the hills modifier (no real-world analogue). Mountain terrain at flat elevation is invalid. The validity matrix is defined in `terrain.config` and enforced during generation.

---

## Movement System

### Die

Players roll a **d8** — 8-directional movement. On each step, the player pays the movement cost of the tile they are entering.

### 8-Directional Movement Formula

Cardinal moves and diagonal moves have different costs:

```
cardinal move cost  = terrain_cost(tile)
diagonal move cost  = (a/2) + (b/2 × √b)
```

Where `a` and `b` are the movement costs of the two tiles forming the diagonal corner (the tiles you would pass through if moving cardinally in each component direction).

This formula penalizes diagonals through expensive terrain more than cheap terrain, without requiring a hard "must enter cardinally" restriction.

### Entry Rule

A player must have **at least as much movement remaining** as the cost of the tile they wish to enter. If they cannot afford entry into any adjacent tile, their (movement action) turn ends.

### Tile Improvements that Modify Movement

- **Roads** — halve the movement cost of a tile
- **Canals** — enable water-based movement on inland tiles
- **Bridges** — allow crossing water features without cost penalty

---

## Map Generation Pipeline

Map generation is a multi-pass pipeline producing a fully populated `width × height` grid of `Tile` objects. All logic is in `land_game/generation/pipeline.py`. Configuration lives in `data/terrain.config`.

### Pass 1 — Elevation Heightmap

Generate a continuous Perlin noise elevation field across the `N×M` grid.

```python
elevation[row][col] = pnoise2(col * scale, row * scale, octaves=6, ...)
```

Parameters (`scale`, `octaves`, `persistence`, `lacunarity`) are tunable in config.

### Pass 2 — Ocean and Coastline

- Tiles below `sea_level_threshold` become ocean (impassable)
- Land tiles adjacent to ocean become coastal variants:
  - Steep slope → **Cliff Coast** (movement cost 3)
  - Gentle slope → **Floodplain** (movement cost 2)
  - Otherwise → **Coastal** (movement cost 1)

Slope is computed from the local elevation gradient at each boundary tile.

### Pass 3 — River Extraction

Rivers are traced **before elevation is demoted**:

1. Identify elevation peaks above `river_source_threshold`
2. Trace downhill to ocean following steepest descent
3. Imprint river modifier on traversed tiles
4. Short rivers (below `min_river_length`) are discarded

Rivers are tile **modifiers**, not standalone terrain types. A tile can be Plains + river.

### Pass 4 — Elevation Demotion

After rivers are extracted, the elevation heightmap is **demoted** to a continuous bias scalar. It no longer deterministically assigns terrain — it merely weights probabilities during seed expansion.

### Pass 5 — Seed Placement

Seed count:

```
num_seeds = int(k × √(N × M))
```

Where `k` is a tunable constant (default ~1.5). Seeds are placed on land tiles only, with random selection **weighted by latitude and elevation bias**. World setting dials (climate, precipitation, age, fragmentation) further bias the initial terrain assignment at each seed.

### Pass 6 — Seed Expansion

Each seed populates its 8 neighbours using the **14×14 adjacency matrix** (column-stochastic; see below).

The weight vector for an unassigned tile is computed as a **weighted average of all assigned neighbours' adjacency columns**, with weights proportional to inverse distance. The winning terrain is sampled from this combined probability vector.

Scaling applied at each step:
- Latitude scalar (north = cold biomes favored; south = warm/desert)
- Elevation bias scalar (retained from Pass 4)
- World settings multipliers (climate, precipitation, age, fragmentation)

All scalars are applied as element-wise multipliers to the weight vector, which is then renormalized to sum to 1 before sampling.

### Pass 7 — While Loop Expansion

The influence radius grows each iteration. Specifically:

- Iteration 1: only direct (distance-1) neighbours influence an unassigned tile
- Later iterations: the influence radius extends to 2, then 3 tiles

At radius > 1, a tile's influence vector is a weighted average of all assigned tiles within radius, weighted by `1/d` (inverse distance). This produces gradual biome transitions rather than jagged borders — terrain types cluster and blend at the edges.

Expansion continues in a while loop until all land tiles are assigned.

### Pass 8 — Isolated Tile Fallback

Any tile that remains unassigned (isolated from all seeded regions) is force-assigned using either the nearest assigned neighbour's terrain or a pure latitude + world settings sample. This is a rare edge case on larger maps.

### Pass 9 — Hills Scalar Assignment

After terrain types are assigned, each land tile receives a `hills_scalar`:

```
hills_scalar = α × terrain_sample + β × sobel_elevation + γ × neighbor_influence
```

Where:
- `terrain_sample` — sampled from the terrain type's `hill_range` (a [min, max] interval defined in config)
- `sobel_elevation` — Sobel operator applied to the Perlin noise elevation map, normalized to [0, 1]; captures ruggedness from the gradient magnitude
- `neighbor_influence` — average `hills_scalar` of already-assigned neighbours, weighted by `1/d`

Default weights: **α = 0.4, β = 0.4, γ = 0.2**

The validity matrix is checked after assignment; invalid terrain-elevation combinations are resampled.

---

## Adjacency Matrix

The **14×14 column-stochastic adjacency matrix** encodes the probability that a given terrain type will spawn adjacent to each other terrain type. Columns represent the **source** terrain; rows represent the **spawned** terrain. Each column sums to 100.

The matrix is **intentionally asymmetric** — the probability that Plains spawns adjacent to Marsh is not the same as the probability that Marsh spawns adjacent to Plains.

The full matrix is defined in `data/terrain.config` under the key `adjacency_matrix`.

> **Critical**: The matrix is column-stochastic. Read column-wise. Rows carry no normalization constraint.

---

## World Settings

World settings are pre-game dials that tune the generation parameters before any tiles are placed. They are applied as **multiplicative scalars to the adjacency matrix columns**, then renormalized.

| Setting | Options | Effect |
|---|---|---|
| **Climate** | Cold / Temperate / Hot | Shifts latitude band thresholds; cold pushes tundra to mid-latitudes; hot expands desert |
| **Precipitation** | Arid / Normal / Wet | Wet: marsh and thick forest abundant; arid: desert and plains dominate |
| **World Age** | Young / Old | Young: more mountains and hills (high β weight); old: flatter, more plains and grassland (high γ weight) |
| **Fragmentation** | Low / Medium / High | Controls how tightly biomes cluster; high fragmentation = patchy, varied map |

**Named Preset: "Low Countries"**
Temperate climate, high precipitation, old world age, low fragmentation. Produces a marshland-heavy, flat map with abundant coastal and floodplain tiles — the thematic default inspired by Dutch/Flemish history.

---

## terrain.config Reference

All terrain parameters are externalized to `data/terrain.config`. Structure:

```
[terrain_types]
  plains.base_cost = 1
  plains.hill_range = [0.0, 0.35]
  plains.color_terrain_mode = [180, 200, 120, 255]
  ...

[adjacency_matrix]
  # 14×14, column-major, each column sums to 100
  ...

[validity_matrix]
  # 14×3 (flat, hills, mountain) boolean grid
  ...

[world_settings]
  climate.cold.tundra_multiplier = 1.8
  climate.cold.desert_multiplier = 0.3
  ...

[hills_scalar]
  alpha = 0.4
  beta = 0.4
  gamma = 0.2
  flat_threshold = 0.20
  mountain_threshold = 0.75

[generation]
  seed_k = 1.5
  sea_level_threshold = 0.0
  river_source_threshold = 0.6
  min_river_length = 4
  perlin_scale = 0.05
  perlin_octaves = 6
```
