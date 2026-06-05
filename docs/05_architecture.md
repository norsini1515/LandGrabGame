# Architecture & Implementation Guide

---

## Technology Stack

| Layer | Technology | Rationale |
|---|---|---|
| Backend / Simulation | Python 3.11+ | numpy/scipy for heavy modeling; fast iteration |
| Numerical | numpy, scipy | Matrix ops, convolutions, noise, Sobel |
| Data modeling | pandas | Trade flow analysis, historical event tables |
| Noise | noise (pnoise) | Perlin noise for elevation and terrain generation |
| API (optional) | FastAPI + uvicorn | Backend server if separating from frontend |
| Validation | pydantic | Config and API schema validation |
| Renderer (phase 1) | pygame | Rapid prototype; colored tile grid |
| Renderer (phase 2, TBD) | React + canvas/WebGL | Polished UI with proper components |
| Distribution target | Steam (desktop) | Python + pygame is distributable via PyInstaller/cx_Freeze |

---

## Package Structure

```
Land_Game/
├── land_game/                  # Core Python package
│   ├── core/                   # Fundamental data classes
│   │   ├── terrain_type.py     # TerrainType enum, ElevationClass enum
│   │   └── tile.py             # Terrain dataclass, Tile dataclass
│   ├── generation/             # Procedural map generation pipeline
│   │   └── pipeline.py         # Full multi-pass terrain generation
│   ├── config/                 # Config loader
│   │   └── loader.py           # Reads data/terrain.config at runtime
│   ├── simulation/             # Game loop, turn logic, economic simulation
│   ├── ai/                     # AI archetypes
│   └── api/                    # FastAPI entry point (optional)
├── frontend/                   # UI layer
│   ├── src/
│   │   ├── components/
│   │   └── mapModes/           # Per-mode render functions
│   └── public/
├── data/
│   ├── terrain.config          # All terrain parameters, matrices, world settings
│   └── design_notes.md         # Deferred ideas and open questions
├── tests/
│   ├── core/
│   ├── generation/
│   └── simulation/
├── docs/                       # This folder
├── pyproject.toml
└── README.md
```

---

## Core Data Classes

### `TerrainType` (enum)

Defined in `land_game/core/terrain_type.py`. One enum variant per terrain type. This is the **flyweight key** — only ~14 unique objects exist across the entire map.

```python
from enum import Enum

class TerrainType(Enum):
    PLAINS = "plains"
    GRASSLAND = "grassland"
    FOREST = "forest"
    THICK_FOREST = "thick_forest"
    JUNGLE = "jungle"
    MARSH = "marsh"
    DESERT = "desert"
    DEEP_DESERT = "deep_desert"
    TUNDRA = "tundra"
    FROZEN_TUNDRA = "frozen_tundra"
    COASTAL = "coastal"
    FLOODPLAIN = "floodplain"
    CLIFF_COAST = "cliff_coast"
    MOUNTAIN = "mountain"
```

### `ElevationClass` (enum, derived)

Never stored; computed from `hills_scalar` at access time.

```python
class ElevationClass(Enum):
    FLAT = "flat"       # hills_scalar < 0.20
    HILLS = "hills"     # 0.20 <= hills_scalar < 0.75
    MOUNTAIN = "mountain"  # hills_scalar >= 0.75
```

### `Terrain` (dataclass)

The physical geography of a tile. Immutable after generation.

```python
@dataclass(frozen=True)
class Terrain:
    terrain_type: TerrainType
    hills_scalar: float          # 0.0 → 1.0
    river: bool = False

    @property
    def elevation_class(self) -> ElevationClass:
        if self.hills_scalar < 0.20:
            return ElevationClass.FLAT
        elif self.hills_scalar < 0.75:
            return ElevationClass.HILLS
        else:
            return ElevationClass.MOUNTAIN
```

### `Tile` (dataclass)

The game state of a tile. Mutable.

```python
@dataclass
class Tile:
    terrain: Terrain
    owner: Optional[int] = None          # player ID, None = unowned
    improvements: list[str] = field(default_factory=list)
    development_state: str = "raw"       # raw / arable / urban
    buildings: list[str] = field(default_factory=list)  # max 3
    _land_value: float = 0.0
    _value_dirty: bool = True

    @property
    def land_value(self) -> float:
        if self._value_dirty:
            self._land_value = self._compute_value()
            self._value_dirty = False
        return self._land_value

    def mark_dirty(self):
        self._value_dirty = True
```

---

## Design Patterns

### Config-Driven Design

All terrain costs, movement costs, adjacency probabilities, development options, and world settings live in `data/terrain.config`. The code reads config at runtime — tuning the game **never requires touching source code**.

The config loader (`land_game/config/loader.py`) exposes a typed interface:

```python
from land_game.config.loader import config

config.terrain.plains.base_cost         # → 1
config.adjacency_matrix                  # → np.ndarray (14×14)
config.hills_scalar.alpha               # → 0.4
config.world_settings.climate.cold      # → multiplier dict
```

### Flyweight Pattern

Only ~14 unique `TerrainType` enum objects exist. All 2,400+ tiles on a default map hold **references** to these objects, not copies. Swapping a tile's terrain on development is a single reference assignment.

The terrain parameter lookups (base cost, hill_range, adjacency column) are also cached at startup from config — one dict per terrain type, shared across all tile instances.

### Dirty Flag

`land_value` is an expensive computation that depends on neighboring tiles, buildings, trailing output, and spillover. The dirty flag ensures it is only recomputed when an input changes:

```python
def add_building(self, building: str):
    self.buildings.append(building)
    self.mark_dirty()
    # Also mark adjacent tiles dirty (spillover changed)
    for neighbour in self.neighbours:
        neighbour.mark_dirty()
```

### Render-Time Map Modes

The same tile data is visualized differently per map mode. Each mode is a **pure function** `(tile, map_mode) → rgba`. No color is ever stored on a tile. This means:

- Adding a new map mode requires only a new render function
- Map mode switching has zero state mutation
- Tests can verify render output without side effects

---

## Generation Pipeline (`land_game/generation/pipeline.py`)

The pipeline is a class with sequential pass methods:

```python
class TerrainPipeline:
    def __init__(self, width: int, height: int, world_settings: WorldSettings, seed: int):
        self.width = width
        self.height = height
        self.settings = world_settings
        self.rng = np.random.default_rng(seed)

    def run(self) -> list[list[Tile]]:
        elevation = self._generate_elevation()
        self._assign_ocean_and_coast(elevation)
        self._extract_rivers(elevation)
        elevation_bias = self._demote_elevation(elevation)
        self._place_seeds(elevation_bias)
        self._expand_seeds(elevation_bias)
        self._assign_hills_scalars(elevation_bias)
        self._validate_and_clamp()
        return self.grid
```

Each pass method is independently testable.

---

## Simulation Layer (`land_game/simulation/`)

Suggested module breakdown:

| Module | Responsibility |
|---|---|
| `game.py` | Game state, turn counter, player list, win condition check |
| `turn.py` | Turn execution: movement, action dispatch, income collection |
| `movement.py` | d8 roll, pathfinding, movement cost computation |
| `economy.py` | Trade routing, market prices, supply/demand, transport costs |
| `valuation.py` | Land value computation, spatial spillover |
| `events.py` | Historical event engine, event pool, draw logic |
| `finance.py` | Loans, bonds, futures, swaps |
| `population.py` | Population growth/decline, food supply chain |
| `military.py` | Condottieri contracts, naval actions, blockades |

---

## Testing Strategy

Use pytest. Tests are in `tests/` mirroring the package structure.

### Priority Test Areas

1. **Terrain generation** — verify the pipeline produces valid grids:
   - No unassigned tiles
   - All columns of adjacency matrix respected (no invalid adjacencies)
   - Validity matrix constraints respected
   - Ocean tiles are contiguous with the map edge (no inland ocean)

2. **Movement cost** — unit tests for diagonal formula with edge cases

3. **Land valuation** — dirty flag behavior; spillover correct with known inputs

4. **Economic simulation** — trade routing produces expected transport costs; market price moves in correct direction when supply changes

5. **Event engine** — events draw from correct pool; multipliers applied to adjacency correctly

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=land_game --cov-report=term-missing

# Run a specific module
pytest tests/generation/
```

---

## Configuration Reference (`data/terrain.config`)

All tunable parameters in one place. Loaded once at startup, cached in memory.

```ini
[generation]
seed_k = 1.5
sea_level_threshold = 0.0
river_source_threshold = 0.6
min_river_length = 4
perlin_scale = 0.05
perlin_octaves = 6
perlin_persistence = 0.5
perlin_lacunarity = 2.0

[hills_scalar]
alpha = 0.4
beta = 0.4
gamma = 0.2
flat_threshold = 0.20
mountain_threshold = 0.75

[movement]
c_constant = -1

[valuation]
spillover_radius = 3

[world_settings.climate.cold]
tundra_multiplier = 1.8
frozen_tundra_multiplier = 2.0
desert_multiplier = 0.3
plains_multiplier = 0.8

[world_settings.precipitation.wet]
marsh_multiplier = 1.9
thick_forest_multiplier = 1.6
desert_multiplier = 0.2
plains_multiplier = 0.7

[terrain.plains]
base_cost = 1
hill_range = [0.0, 0.35]
color_terrain_mode = [180, 200, 120, 255]
color_political_mode = null   # overridden by owner color

[terrain.marsh]
base_cost = 3
hill_range = [0.0, 0.10]     # marsh cannot be hilly — real-world constraint
color_terrain_mode = [100, 140, 100, 255]

# ... (all 14 terrain types)

[adjacency_matrix]
# 14×14 column-stochastic, values are integers summing to 100 per column
# Row order = column order = TerrainType enum order
```

---

## Development Milestones

### Milestone 1 — Renderable Map
- Perlin noise elevation heightmap
- Ocean and coastline assignment
- River extraction and imprint
- Terrain seed placement and expansion
- Hills scalar assignment
- pygame colored tile grid display
- Map mode switching (terrain, hydrology at minimum)

### Milestone 2 — Player Movement
- d8 movement with terrain costs
- Tile ownership purchase
- Basic UI overlay (player position, movement remaining, owned tiles)
- Political map mode

### Milestone 3 — Development & Buildings
- Development ladder state machine
- Tile improvements (roads, farms, mines)
- Building placement and tier logic
- Population system (food supply + amenities)
- Value map mode

### Milestone 4 — Economy
- Trade goods production and routing
- Market price simulation
- Transport cost calculation
- Financial engine baseline (event engine)
- Land valuation with spillover

### Milestone 5 — Finance & Military
- Loans and bonds
- Futures contracts
- Condottieri contracts and naval actions
- Blockade mechanic

### Milestone 6 — AI & Polish
- AI archetype system
- Win condition check and game end
- Full event pool
- UI polish / map mode completeness
- Save/load system

---

## Dependency Installation

```bash
# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# Install in editable mode with dev dependencies
pip install -e ".[dev]"
```

`pyproject.toml` dependencies:
- `numpy` — matrix ops, noise arrays
- `scipy` — Sobel operator, convolutions, spatial operations
- `pandas` — event tables, trade flow analysis
- `noise` — Perlin noise (`pnoise2`)
- `fastapi` — API layer (optional, future)
- `uvicorn` — ASGI server for FastAPI
- `pydantic` — config and API validation
- `pygame` — rendering (phase 1)

Dev dependencies:
- `pytest`
- `pytest-cov`
- `black`
- `ruff`
