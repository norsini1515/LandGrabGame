"""Procedural map generation: noise → coastal → seeds → BFS expansion → hills scalar."""

from __future__ import annotations

import math
import random
from collections import deque

try:
    import opensimplex  # type: ignore[import]
    _HAS_NOISE = True
except ImportError:
    _HAS_NOISE = False

from landgrab.core import config
from landgrab.models.game_state import ModifierType, TerrainType, Tile

# Terrains that participate in land seed/BFS expansion (not ocean, not coastal, not river)
_LAND_TERRAINS: list[str] = [
    "plain", "grassland", "forest", "thick_forest", "jungle",
    "marsh", "desert", "deep_desert", "tundra", "frozen_tundra",
]

_COASTAL_TERRAINS: set[str] = {"coastal", "floodplain", "cliff_coast"}

_STR_TO_TERRAIN: dict[str, TerrainType] = {t.value: t for t in TerrainType}


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def generate_map(
    width: int,
    height: int,
    seed: int,
    world: object | None = None,  # WorldSettings or None
) -> list[Tile]:
    """Full pipeline: heightmap → ocean/coastal → seed+BFS → hills → rivers."""

    # Resolve world settings
    if world is None:
        from landgrab.models.game_state import WorldSettings
        world = WorldSettings()

    climate       = getattr(world, "climate",       "temperate")
    precipitation = getattr(world, "precipitation", "normal")
    age           = getattr(world, "age",           "old")
    fragmentation = getattr(world, "fragmentation", "default")

    rng = random.Random(seed)
    np  = config.noise_params()
    op  = config.ocean_params()

    # 1. Elevation heightmap
    elev: dict[tuple[int, int], float] = {}
    for y in range(height):
        for x in range(width):
            elev[(x, y)] = _noise_elevation(x, y, width, height, seed, np)

    # 2. Ocean / coastal assignment
    terrain_str: dict[tuple[int, int], str] = {}
    for y in range(height):
        for x in range(width):
            e = elev[(x, y)]
            if e < op["elevation_threshold"]:
                terrain_str[(x, y)] = "ocean"
            elif e < op["coastal_threshold"]:
                # Determine coastal sub-type by gradient
                g = _gradient(elev, x, y, width, height)
                if g >= op["cliff_min_gradient"]:
                    terrain_str[(x, y)] = "cliff_coast"
                elif g <= op["floodplain_max_gradient"]:
                    terrain_str[(x, y)] = "floodplain"
                else:
                    terrain_str[(x, y)] = "coastal"
            else:
                terrain_str[(x, y)] = ""  # land, to be assigned by BFS

    # 3. Seed placement on land tiles
    k = config.fragmentation_k().get(fragmentation, 1.0)
    num_seeds = max(4, int(k * math.sqrt(width * height)))
    land_tiles = [(x, y) for (x, y), t in terrain_str.items() if t == ""]
    if not land_tiles:
        land_tiles = [(width // 2, height // 2)]

    # Climate + precipitation multipliers for land terrain selection
    clim_mult  = config.climate_multipliers()
    precip_mult = config.precipitation_multipliers()
    val_matrix = config.validity_matrix()

    seed_positions: list[tuple[int, int]] = _place_seeds(land_tiles, num_seeds, rng)
    for pos in seed_positions:
        terrain_str[pos] = _pick_terrain(
            elev[pos], width, height, pos[0], pos[1],
            climate, precipitation, clim_mult, precip_mult, rng,
        )

    # 4. BFS expansion from seeds
    _bfs_expand(
        terrain_str, elev, land_tiles, climate, precipitation,
        clim_mult, precip_mult, rng, width, height,
    )

    # 5. Hills scalar + modifier determination
    age_delta = config.age_hill_range_delta()
    hill_delta = age_delta.get(age, 0.0)
    h_ranges  = config.hills_ranges()
    h_weights = config.hills_weights()
    h_thresh  = config.hills_thresholds()
    hills_scalar: dict[tuple[int, int], float] = {}

    for y in range(height):
        for x in range(width):
            t = terrain_str[(x, y)]
            if t in ("ocean", "coastal", "floodplain", "cliff_coast", ""):
                hills_scalar[(x, y)] = 0.0
            else:
                lo, hi = h_ranges.get(t, (0.0, 0.3))
                hi = min(1.0, hi + hill_delta)
                lo = min(lo, hi)
                sampled = rng.uniform(lo, hi)
                slope = _sobel(elev, x, y, width, height)
                scalar = h_weights["alpha"] * sampled + h_weights["beta"] * slope
                hills_scalar[(x, y)] = min(1.0, max(0.0, scalar))

    # Second pass: add neighbour influence (gamma)
    gamma = h_weights["gamma"]
    if gamma > 0.0:
        for y in range(height):
            for x in range(width):
                t = terrain_str[(x, y)]
                if t in ("ocean", "coastal", "floodplain", "cliff_coast", ""):
                    continue
                nbr_sum = nbr_w = 0.0
                for ddx, ddy, dist in _nbr_weights(x, y, width, height):
                    nbr_sum += hills_scalar[(x + ddx, y + ddy)] / dist
                    nbr_w   += 1.0 / dist
                if nbr_w:
                    hills_scalar[(x, y)] = min(
                        1.0, hills_scalar[(x, y)] + gamma * (nbr_sum / nbr_w)
                    )

    # 6. Build Tile objects
    tiles: list[Tile] = []
    for y in range(height):
        for x in range(width):
            t_str = terrain_str[(x, y)] or "plain"
            hs    = hills_scalar[(x, y)]
            mod   = _modifier(t_str, hs, h_thresh, val_matrix)
            mc    = config.get_move_cost(t_str, mod.value)
            tiles.append(Tile(
                x=x, y=y,
                terrain=_STR_TO_TERRAIN.get(t_str, TerrainType.PLAIN),
                modifier=mod,
                elevation=round(elev[(x, y)], 4),
                hills_scalar=round(hs, 3),
                move_cost=mc,
            ))

    # 7. River overlay
    _add_rivers(tiles, elev, width, height, seed)

    # 8. Fix interior ocean
    _fix_interior_ocean(tiles)

    return tiles


# ---------------------------------------------------------------------------
# Noise / elevation
# ---------------------------------------------------------------------------

def _noise_elevation(
    x: int, y: int, width: int, height: int, seed: int,
    np: dict[str, float],
) -> float:
    scale       = np["scale"]
    octaves     = int(np["octaves"])
    persistence = np["persistence"]
    lacunarity  = np["lacunarity"]

    if not _HAS_NOISE:
        rng  = random.Random(seed ^ (x * 73856093) ^ (y * 19349663))
        base = rng.random()
    else:
        opensimplex.seed(seed)
        value = 0.0
        amplitude = 1.0
        frequency = 1.0
        max_value = 0.0
        for _ in range(octaves):
            nx_val = x * scale * frequency
            ny_val = y * scale * frequency
            value     += opensimplex.noise2(nx_val, ny_val) * amplitude
            max_value += amplitude
            amplitude *= persistence
            frequency *= lacunarity
        base = (value / max_value + 1.0) / 2.0

    return base * _edge_fade(x, y, width, height)


def _edge_fade(x: int, y: int, width: int, height: int) -> float:
    dx = abs(x / width  - 0.5) * 2
    dy = abs(y / height - 0.5) * 2
    dist = max(dx, dy)
    fade_start = config.edge_fade_start()
    if dist < fade_start:
        return 1.0
    t = (dist - fade_start) / (1.0 - fade_start)
    return max(0.0, 1.0 - t * t)


def _gradient(elev: dict, x: int, y: int, width: int, height: int) -> float:
    """Simple max cardinal gradient magnitude."""
    e = elev[(x, y)]
    diffs = []
    for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
        nx, ny = x + dx, y + dy
        if 0 <= nx < width and 0 <= ny < height:
            diffs.append(abs(elev[(nx, ny)] - e))
    return max(diffs) if diffs else 0.0


def _sobel(elev: dict, x: int, y: int, width: int, height: int) -> float:
    """Normalized Sobel slope (0–1)."""
    def g(dx: int, dy: int) -> float:
        nx, ny = x + dx, y + dy
        if 0 <= nx < width and 0 <= ny < height:
            return elev[(nx, ny)]
        return elev[(x, y)]

    gx = -g(-1,-1) - 2*g(-1,0) - g(-1,1) + g(1,-1) + 2*g(1,0) + g(1,1)
    gy = -g(-1,-1) - 2*g(0,-1) - g(1,-1) + g(-1,1) + 2*g(0,1) + g(1,1)
    magnitude = math.sqrt(gx*gx + gy*gy)
    return min(1.0, magnitude / 4.0)  # normalise: max theoretical ~4


# ---------------------------------------------------------------------------
# Seed placement + terrain selection
# ---------------------------------------------------------------------------

def _place_seeds(
    land_tiles: list[tuple[int, int]],
    num_seeds: int,
    rng: random.Random,
) -> list[tuple[int, int]]:
    """Spread seeds roughly evenly by partitioning land tiles."""
    if num_seeds >= len(land_tiles):
        return land_tiles[:]
    step = len(land_tiles) // num_seeds
    candidates = [land_tiles[i * step] for i in range(num_seeds)]
    # Add a little jitter
    jitter = step // 2
    result = []
    for cx, cy in candidates:
        idx = land_tiles.index((cx, cy))
        jitter_idx = max(0, min(len(land_tiles) - 1, idx + rng.randint(-jitter, jitter)))
        result.append(land_tiles[jitter_idx])
    return result


def _pick_terrain(
    elevation: float,
    width: int, height: int, x: int, y: int,
    climate: str, precipitation: str,
    clim_mult: dict, precip_mult: dict,
    rng: random.Random,
) -> str:
    """Sample a land terrain type given location + world settings."""
    # Base weights — equal across all land terrains
    weights = {t: 1.0 for t in _LAND_TERRAINS}

    # Climate multipliers
    for t in _LAND_TERRAINS:
        cm = clim_mult.get(t, {}).get(climate, 1.0)
        pm = precip_mult.get(t, {}).get(precipitation, 1.0)
        weights[t] *= cm * pm

    # Latitude bias (0 = equator-ish center)
    lat = abs(y / height - 0.5) * 2  # 0 at center, 1 at poles
    _apply_latitude_bias(weights, lat)

    # Elevation hint: high elevation = less flat terrain
    if elevation > 0.7:
        for t in ("marsh", "floodplain", "jungle"):
            weights[t] = weights.get(t, 0.0) * 0.1

    terrains = list(weights.keys())
    wt_vals  = [max(0.01, weights[t]) for t in terrains]
    return rng.choices(terrains, weights=wt_vals, k=1)[0]


def _apply_latitude_bias(weights: dict[str, float], lat: float) -> None:
    """Shift weights toward cold terrains at high latitudes."""
    if lat > 0.6:
        factor = (lat - 0.6) / 0.4  # 0→1 for lat 0.6→1.0
        for cold in ("tundra", "frozen_tundra"):
            weights[cold] = weights.get(cold, 0.0) * (1.0 + 4.0 * factor)
        for warm in ("jungle", "desert", "deep_desert"):
            weights[warm] = weights.get(warm, 0.0) * (1.0 - 0.8 * factor)


# ---------------------------------------------------------------------------
# BFS expansion
# ---------------------------------------------------------------------------

def _bfs_expand(
    terrain_str: dict[tuple[int, int], str],
    elev: dict[tuple[int, int], float],
    land_tiles: list[tuple[int, int]],
    climate: str,
    precipitation: str,
    clim_mult: dict,
    precip_mult: dict,
    rng: random.Random,
    width: int,
    height: int,
) -> None:
    """Fill unassigned land tiles via inverse-distance-weighted adjacency voting."""
    adj_matrix = config.adjacency_matrix()
    max_radius = config.max_expansion_radius()

    assigned: set[tuple[int, int]] = {
        pos for pos, t in terrain_str.items() if t != ""
    }
    queue: deque[tuple[int, int, int]] = deque()  # (x, y, dist_from_seed)

    # Seed the BFS frontier from assigned land tiles' unassigned neighbours
    for (sx, sy) in list(assigned):
        if terrain_str[(sx, sy)] in ("ocean", "coastal", "floodplain", "cliff_coast"):
            continue
        for dx, dy in [(-1,0),(1,0),(0,-1),(0,1),(-1,-1),(1,-1),(-1,1),(1,1)]:
            nx, ny = sx + dx, sy + dy
            if (0 <= nx < width and 0 <= ny < height
                    and terrain_str.get((nx, ny)) == "" and (nx, ny) not in assigned):
                queue.append((nx, ny, 1))
                assigned.add((nx, ny))

    while queue:
        x, y, dist = queue.popleft()
        # Collect weighted votes from assigned land neighbours
        votes: dict[str, float] = {}
        for ddx in range(-dist, dist + 1):
            for ddy in range(-dist, dist + 1):
                nx, ny = x + ddx, y + ddy
                if not (0 <= nx < width and 0 <= ny < height):
                    continue
                nt = terrain_str.get((nx, ny), "")
                if nt in ("", "ocean", "coastal", "floodplain", "cliff_coast"):
                    continue
                d = max(1, abs(ddx) + abs(ddy))
                if d > max_radius:
                    continue
                w = 1.0 / d
                col = adj_matrix.get(nt, {})
                for neighbour_t, prob in col.items():
                    votes[neighbour_t] = votes.get(neighbour_t, 0.0) + prob * w

        if votes:
            # Filter to only land terrains
            valid_votes = {t: v for t, v in votes.items() if t in _LAND_TERRAINS}
            if valid_votes:
                ts = list(valid_votes.keys())
                ws = list(valid_votes.values())
                terrain_str[(x, y)] = rng.choices(ts, weights=ws, k=1)[0]
            else:
                terrain_str[(x, y)] = _pick_terrain(
                    elev[(x, y)], width, height, x, y,
                    climate, precipitation, clim_mult, precip_mult, rng,
                )
        else:
            terrain_str[(x, y)] = _pick_terrain(
                elev[(x, y)], width, height, x, y,
                climate, precipitation, clim_mult, precip_mult, rng,
            )

        # Enqueue neighbours
        for dx, dy in [(-1,0),(1,0),(0,-1),(0,1),(-1,-1),(1,-1),(-1,1),(1,1)]:
            nx, ny = x + dx, y + dy
            if (0 <= nx < width and 0 <= ny < height
                    and terrain_str.get((nx, ny)) == "" and (nx, ny) not in assigned):
                queue.append((nx, ny, min(dist + 1, max_radius)))
                assigned.add((nx, ny))

    # Fallback: any still-unassigned land tile
    for (x, y), t in terrain_str.items():
        if t == "":
            terrain_str[(x, y)] = _pick_terrain(
                elev[(x, y)], width, height, x, y,
                climate, precipitation, clim_mult, precip_mult, rng,
            )


# ---------------------------------------------------------------------------
# Modifier determination
# ---------------------------------------------------------------------------

def _modifier(
    terrain: str,
    hs: float,
    thresholds: dict[str, float],
    val_matrix: dict[str, dict[str, bool]],
) -> ModifierType:
    if terrain in ("ocean", "coastal", "floodplain", "cliff_coast", "river"):
        return ModifierType.FLAT

    flat_t = thresholds["flat"]
    mtn_t  = thresholds["mountain"]
    vm     = val_matrix.get(terrain, {"flat": True, "hills": True, "mountain": True})

    if hs >= mtn_t and vm.get("mountain", False):
        return ModifierType.MOUNTAIN
    if hs >= flat_t and vm.get("hills", False):
        return ModifierType.HILLS
    return ModifierType.FLAT


def _nbr_weights(
    x: int, y: int, width: int, height: int
) -> list[tuple[int, int, float]]:
    result = []
    for dx in range(-1, 2):
        for dy in range(-1, 2):
            if dx == 0 and dy == 0:
                continue
            nx, ny = x + dx, y + dy
            if 0 <= nx < width and 0 <= ny < height:
                dist = math.sqrt(dx*dx + dy*dy)
                result.append((dx, dy, dist))
    return result


# ---------------------------------------------------------------------------
# Rivers
# ---------------------------------------------------------------------------

def _add_rivers(
    tiles: list[Tile],
    elev: dict[tuple[int, int], float],
    width: int,
    height: int,
    seed: int,
) -> None:
    rp   = config.river_params()
    rng  = random.Random(seed + 42)
    grid = {(t.x, t.y): t for t in tiles}
    num_rivers = max(1, (width * height) // int(rp["count_divisor"]))
    min_descent = rp["min_descent"]

    for _ in range(num_rivers):
        high_tiles = [
            t for t in tiles
            if t.modifier in (ModifierType.HILLS, ModifierType.MOUNTAIN)
            and t.terrain not in (TerrainType.OCEAN, TerrainType.COASTAL,
                                  TerrainType.CLIFF_COAST, TerrainType.FLOODPLAIN)
        ]
        if not high_tiles:
            break
        start = rng.choice(high_tiles)
        cx, cy = start.x, start.y

        for _ in range(width + height):
            current = grid.get((cx, cy))
            if current is None:
                break
            if current.terrain in (TerrainType.OCEAN, TerrainType.COASTAL,
                                    TerrainType.CLIFF_COAST, TerrainType.FLOODPLAIN):
                break
            if current.modifier != ModifierType.MOUNTAIN:
                current.terrain   = TerrainType.RIVER
                current.modifier  = ModifierType.FLAT
                current.move_cost = config.get_move_cost("river", "flat")

            neighbors = [grid.get((cx + dx, cy + dy)) for dx, dy in [(-1,0),(1,0),(0,-1),(0,1)]]
            valid = [n for n in neighbors if n is not None]
            if not valid:
                break
            nxt = min(valid, key=lambda t: elev[(t.x, t.y)])
            if elev[(nxt.x, nxt.y)] >= (elev[(cx, cy)] - min_descent):
                break
            cx, cy = nxt.x, nxt.y


# ---------------------------------------------------------------------------
# Interior ocean fix
# ---------------------------------------------------------------------------

def _fix_interior_ocean(tiles: list[Tile]) -> None:
    grid = {(t.x, t.y): t for t in tiles}
    land = {
        TerrainType.PLAIN, TerrainType.GRASSLAND, TerrainType.FOREST,
        TerrainType.THICK_FOREST, TerrainType.JUNGLE, TerrainType.MARSH,
        TerrainType.DESERT, TerrainType.DEEP_DESERT, TerrainType.TUNDRA,
        TerrainType.FROZEN_TUNDRA, TerrainType.COASTAL, TerrainType.FLOODPLAIN,
        TerrainType.CLIFF_COAST, TerrainType.RIVER,
    }
    for tile in tiles:
        if tile.terrain != TerrainType.OCEAN:
            continue
        for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            nbr = grid.get((tile.x + dx, tile.y + dy))
            if nbr and nbr.terrain in land:
                tile.terrain   = TerrainType.COASTAL
                tile.move_cost = config.get_move_cost("coastal", "flat")
                break
