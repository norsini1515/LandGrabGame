# Algorithms & Mathematical Reference

---

## Movement

### Die

Players roll a **d8** — 8-directional movement on a square grid.

### Cardinal Move Cost

```
cost = terrain_cost(destination_tile)
```

### Diagonal Move Cost

```
cost = (a / 2) + (b / 2 × √b)
```

Where `a` and `b` are the movement costs of the two tiles forming the diagonal corner (the tiles you would cross if moving cardinally in each component axis direction).

This formula penalizes expensive diagonals more heavily than cheap ones without requiring a strict "cardinal only" restriction.

### Combined Terrain Cost (with hills modifier)

```
combined_cost = a + (b + c)
```

Where:
- `a` = base terrain movement cost
- `b` = hills additive penalty (implicit, defined per terrain type in config)
- `c` = tunable constant, **default -1**

### Entry Rule

A player must have `remaining_movement >= terrain_cost(tile)` to enter a tile. If no adjacent tile is affordable, the turn ends.

---

## Hills Scalar

The `hills_scalar` on each tile is computed as a weighted combination of three signals:

```
hills_scalar(tile) = α × terrain_sample(tile)
                   + β × sobel_elevation(tile)
                   + γ × neighbor_influence(tile)
```

**Components:**

| Term | Source | Description |
|---|---|---|
| `terrain_sample` | Config `hill_range` | Sampled uniformly from `[min, max]` interval defined per terrain type |
| `sobel_elevation` | Perlin noise heightmap | Gradient magnitude from Sobel operator, normalized to [0, 1] |
| `neighbor_influence` | Adjacent tiles | Weighted average of assigned neighbours' `hills_scalar`, weights = `1/d` |

**Default weights**: α = 0.4, β = 0.4, γ = 0.2

All weights are tunable in `terrain.config`. World age affects these weights: a young world has higher β (elevation-driven ruggedness); an old world has higher γ (neighbour-smoothed terrain).

### Sobel Operator Application

The Sobel operator is applied to the Perlin noise elevation array before it is demoted to a bias scalar:

```python
from scipy.ndimage import sobel
import numpy as np

Gx = sobel(elevation, axis=1)
Gy = sobel(elevation, axis=0)
gradient_magnitude = np.hypot(Gx, Gy)
sobel_elevation = gradient_magnitude / gradient_magnitude.max()  # normalize to [0, 1]
```

---

## Terrain Generation

### Seed Count

```
num_seeds = int(k × √(N × M))
```

Default `k = 1.5`. This produces ~92 seeds on a 60×40 map.

### Adjacency Matrix Application

The adjacency matrix `A` is 14×14, column-stochastic. Each column `j` represents terrain type `j` as the source; entry `A[i][j]` is the probability (out of 100) that terrain type `i` spawns adjacent to terrain type `j`.

For an unassigned tile with assigned neighbours `{n₁, n₂, ..., nₖ}` at distances `{d₁, d₂, ..., dₖ}`:

```
w(tile) = Σ (1/dᵢ) × A[:, terrain(nᵢ)]   (sum over all assigned neighbours)
w(tile) = w(tile) / sum(w(tile))            (normalize to probability distribution)
terrain(tile) ~ Categorical(w(tile))        (sample)
```

### World Settings Scaling

World settings are applied as column-wise multipliers to `A` before computing `w(tile)`:

```
A_scaled[:, j] = A[:, j] × world_multipliers
A_scaled[:, j] = A_scaled[:, j] / sum(A_scaled[:, j])   (renormalize)
```

World multipliers are pre-computed once per game session when world settings are locked in.

### Latitude Scalar

Latitude is normalized to [0, 1] where 0 = equator (south edge) and 1 = polar (north edge). For each terrain type, a latitude preference curve is defined in config (can be a simple ramp or a Gaussian peak). Applied as an additional element-wise multiplier to the weight vector before sampling.

### Validity Matrix

The validity matrix `V` is 14×3:
- Rows: terrain types (same order as adjacency matrix columns)
- Columns: elevation classes (flat, hills, mountain)
- Entry `V[i][e] = 1` means terrain type `i` is valid at elevation class `e`; `= 0` means invalid

After hills_scalar assignment, if `V[terrain_type][elevation_class] = 0`, the hills_scalar is clamped to the valid range for that terrain type.

---

## Land Valuation

```
V(tile) = α·Capital(tile) + β·AvgOutput(tile, 5) + γ·Activity(tile)
        + Σᵢ Spillover(tileᵢ) / dᵢ²
```

Where the sum is over all tiles within the spillover radius `X`.

### Dirty Flag

`land_value` is stored on each `Tile` with a boolean `_value_dirty` flag. The flag is set when any input changes (new building, improvement, neighbour development, etc.). The value is recomputed lazily on next access.

```python
@property
def land_value(self):
    if self._value_dirty:
        self._land_value = self._compute_value()
        self._value_dirty = False
    return self._land_value
```

### Spatial Spillover as Matrix Operation

The spillover component can be computed over the entire map as a convolution:

```python
import numpy as np
from scipy.ndimage import convolve

# Build a development_score matrix (N×M) from all tiles
development = np.array([[tile.development_score for tile in row] for row in grid])

# Inverse-square kernel of radius X
x = np.arange(-X, X+1)
xx, yy = np.meshgrid(x, x)
d2 = xx**2 + yy**2
kernel = np.where(d2 == 0, 0, 1.0 / d2)
kernel /= kernel.sum()

spillover = convolve(development, kernel, mode='constant', cval=0)
```

This gives the spillover contribution for every tile in one vectorized pass.

---

## AI Decision Scoring

For each candidate action `a` on turn `t`, the AI scores:

```
score(a) = Σₖ wₖ × fₖ(a, state)
```

Where:
- `wₖ` = AI player's weight for archetype `k` ∈ {merchant, landlord, builder, speculator}
- `fₖ(a, state)` = expected value contribution of action `a` under archetype `k`'s objective function
- The AI selects `argmax_a score(a)` over all feasible actions

Each `fₖ` is a domain-specific scoring function:
- `f_merchant(a)` — expected trade profit / market position improvement
- `f_landlord(a)` — expected toll income / land value gain from acquisition
- `f_builder(a)` — expected population or building tier gain / urban expansion
- `f_speculator(a)` — expected event engine exploitation value / arbitrage opportunity

---

## Financial Instruments

### Futures Pricing (simplified)

```
futures_price(good, T) = spot_price(good) × (1 + r)^T + carry_cost(T)
```

Where:
- `r` = current interest rate (from event engine baseline)
- `T` = turns until delivery
- `carry_cost` = storage and logistics cost for holding the good until delivery

### Futures P&L at Settlement

```
pnl = (settlement_price - futures_price) × quantity
```

For a long position (buyer): profit if prices rise; loss if prices fall.

### Spatial Trade Cost

```
transport_cost(route) = Σ tile_cost(t) × goods_weight_multiplier
```

Reduced by road improvements: `road_modifier = 0.5` (roads halve tile transport cost).

---

## Map Mode Rendering

Render colors are computed at render time as pure functions of `(tile, map_mode)`. They are **never stored on the tile**.

```python
def get_tile_color(tile: Tile, map_mode: MapMode) -> tuple[int, int, int, int]:
    match map_mode:
        case MapMode.TERRAIN:
            base = TERRAIN_COLORS[tile.terrain.terrain_type]
            # Darken by hills_scalar
            factor = 1.0 - 0.3 * tile.terrain.hills_scalar
            return darken(base, factor)
        case MapMode.POLITICAL:
            return PLAYER_COLORS[tile.owner] if tile.owner else UNOWNED_COLOR
        case MapMode.VALUE:
            return value_heatmap(tile.land_value, global_max_value)
        case MapMode.HYDROLOGY:
            return RIVER_COLOR if tile.terrain.river else WATER_TERRAIN_COLORS.get(
                tile.terrain.terrain_type, DEFAULT_COLOR)
```
