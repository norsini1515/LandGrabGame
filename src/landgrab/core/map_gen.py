"""Procedural map generation: noise → coastal → Voronoi seeds → hills scalar → rivers."""

from __future__ import annotations

import math
import random

try:
    import opensimplex  # type: ignore[import]
    _HAS_NOISE = True
except ImportError:
    _HAS_NOISE = False

from landgrab.core import config
from landgrab.models.game_state import ModifierType, TerrainType, Tile

_LAND_TERRAINS: list[str] = [
    "plain", "grassland", "forest", "thick_forest", "jungle",
    "marsh", "desert", "deep_desert", "tundra", "frozen_tundra",
]

_STR_TO_TERRAIN: dict[str, TerrainType] = {t.value: t for t in TerrainType}


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def generate_map(
    width: int,
    height: int,
    seed: int,
    world: object | None = None,
) -> list[Tile]:
    if world is None:
        from landgrab.models.game_state import WorldSettings
        world = WorldSettings()

    climate       = getattr(world, "climate",       "temperate")
    precipitation = getattr(world, "precipitation", "normal")
    age           = getattr(world, "age",           "old")
    fragmentation = getattr(world, "fragmentation", "default")

    rng = random.Random(seed)
    np_ = config.noise_params()
    op  = config.ocean_params()

    # 1. Elevation heightmap
    elev: dict[tuple[int, int], float] = {}
    for y in range(height):
        for x in range(width):
            elev[(x, y)] = _noise_elevation(x, y, width, height, seed, np_)

    # 2. Ocean / coastal assignment
    terrain_str: dict[tuple[int, int], str] = {}
    for y in range(height):
        for x in range(width):
            e = elev[(x, y)]
            if e < op["elevation_threshold"]:
                terrain_str[(x, y)] = "ocean"
            elif e < op["coastal_threshold"]:
                g = _gradient(elev, x, y, width, height)
                if g >= op["cliff_min_gradient"]:
                    terrain_str[(x, y)] = "cliff_coast"
                elif g <= op["floodplain_max_gradient"]:
                    terrain_str[(x, y)] = "floodplain"
                else:
                    terrain_str[(x, y)] = "coastal"
            else:
                terrain_str[(x, y)] = ""

    # 3. Seed placement on land tiles
    k = config.fragmentation_k().get(fragmentation, 1.0)
    num_seeds = max(4, int(k * math.sqrt(width * height)))
    land_tiles = [(x, y) for (x, y), t in terrain_str.items() if t == ""]
    if not land_tiles:
        land_tiles = [(width // 2, height // 2)]

    clim_mult   = config.climate_multipliers()
    precip_mult = config.precipitation_multipliers()

    seed_positions = _place_seeds(land_tiles, num_seeds, rng)
    for pos in seed_positions:
        terrain_str[pos] = _pick_terrain(
            elev[pos], height, pos[1],
            climate, precipitation, clim_mult, precip_mult, rng,
        )

    # 4. Voronoi expansion — each unassigned land tile gets nearest seed's terrain
    _voronoi_assign(terrain_str, seed_positions, land_tiles, rng)

    # Fallback: any still-unassigned
    for pos, t in terrain_str.items():
        if t == "":
            terrain_str[pos] = _pick_terrain(
                elev[pos], height, pos[1],
                climate, precipitation, clim_mult, precip_mult, rng,
            )

    # 5. Hills scalar using normalized elevation (not raw Sobel)
    age_delta = config.age_hill_range_delta()
    hill_delta = age_delta.get(age, 0.0)
    h_ranges  = config.hills_ranges()
    h_weights = config.hills_weights()
    h_thresh  = config.hills_thresholds()
    coast_thresh  = op["coastal_threshold"]
    val_matrix = config.validity_matrix()
    hills_scalar: dict[tuple[int, int], float] = {}

    for y in range(height):
        for x in range(width):
            t = terrain_str[(x, y)]
            if t in ("ocean", "coastal", "floodplain", "cliff_coast"):
                hills_scalar[(x, y)] = 0.0
                continue
            lo, hi = h_ranges.get(t, (0.0, 0.3))
            hi = min(1.0, hi + hill_delta)
            lo = min(lo, hi)
            sampled = rng.uniform(lo, hi)
            # Normalize elevation relative to land range → 0 near coast, 1 at peaks
            e = elev[(x, y)]
            elev_land = max(0.0, (e - coast_thresh) / max(0.001, 1.0 - coast_thresh))
            # Apply slight power curve so high elevations reach mountain threshold
            elev_factor = elev_land ** 0.65
            scalar = h_weights["alpha"] * sampled + h_weights["beta"] * elev_factor
            hills_scalar[(x, y)] = min(1.0, max(0.0, scalar))

    # Second pass: gamma neighbour smoothing
    gamma = h_weights["gamma"]
    if gamma > 0.0:
        smoothed = dict(hills_scalar)
        for y in range(height):
            for x in range(width):
                t = terrain_str[(x, y)]
                if t in ("ocean", "coastal", "floodplain", "cliff_coast"):
                    continue
                nbr_sum = nbr_w = 0.0
                for ddx, ddy, dist in _nbr_weights(x, y, width, height):
                    nbr_sum += hills_scalar[(x + ddx, y + ddy)] / dist
                    nbr_w   += 1.0 / dist
                if nbr_w:
                    smoothed[(x, y)] = min(
                        1.0, hills_scalar[(x, y)] + gamma * (nbr_sum / nbr_w)
                    )
        hills_scalar = smoothed

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

    # 7. River overlay (marks is_river, keeps underlying terrain)
    _add_rivers(tiles, elev, width, height, seed)

    # 8. Fix interior ocean
    _fix_interior_ocean(tiles)

    # 9. Ensure coastal types only appear within 2 tiles of ocean
    _fix_inland_coastal(tiles, rng)

    return tiles


# ---------------------------------------------------------------------------
# Noise / elevation helpers
# ---------------------------------------------------------------------------

def _noise_elevation(
    x: int, y: int, width: int, height: int, seed: int,
    np_: dict[str, float],
) -> float:
    scale       = np_["scale"]
    octaves     = int(np_["octaves"])
    persistence = np_["persistence"]
    lacunarity  = np_["lacunarity"]

    if not _HAS_NOISE:
        r = random.Random(seed ^ (x * 73856093) ^ (y * 19349663))
        base = r.random()
    else:
        opensimplex.seed(seed)
        value = amplitude = frequency = max_value = 0.0
        amplitude = 1.0
        frequency = 1.0
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
    e = elev[(x, y)]
    diffs = []
    for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
        nx, ny = x + dx, y + dy
        if 0 <= nx < width and 0 <= ny < height:
            diffs.append(abs(elev[(nx, ny)] - e))
    return max(diffs) if diffs else 0.0


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
                result.append((dx, dy, math.sqrt(dx*dx + dy*dy)))
    return result


# ---------------------------------------------------------------------------
# Seed placement + terrain selection
# ---------------------------------------------------------------------------

def _place_seeds(
    land_tiles: list[tuple[int, int]],
    num_seeds: int,
    rng: random.Random,
) -> list[tuple[int, int]]:
    if num_seeds >= len(land_tiles):
        return land_tiles[:]
    step = max(1, len(land_tiles) // num_seeds)
    jitter = step // 2
    result = []
    for i in range(num_seeds):
        idx = i * step + rng.randint(-jitter, jitter)
        idx = max(0, min(len(land_tiles) - 1, idx))
        result.append(land_tiles[idx])
    return result


def _pick_terrain(
    elevation: float,
    height: int, y: int,
    climate: str, precipitation: str,
    clim_mult: dict, precip_mult: dict,
    rng: random.Random,
) -> str:
    weights = {t: 1.0 for t in _LAND_TERRAINS}

    for t in _LAND_TERRAINS:
        weights[t] *= clim_mult.get(t, {}).get(climate, 1.0)
        weights[t] *= precip_mult.get(t, {}).get(precipitation, 1.0)

    lat = abs(y / max(1, height) - 0.5) * 2
    _apply_latitude_bias(weights, lat)

    if elevation > 0.7:
        for t in ("marsh", "floodplain", "jungle"):
            weights[t] = weights.get(t, 0.0) * 0.1

    terrains = list(weights.keys())
    wt_vals  = [max(0.01, weights[t]) for t in terrains]
    return rng.choices(terrains, weights=wt_vals, k=1)[0]


def _apply_latitude_bias(weights: dict[str, float], lat: float) -> None:
    if lat > 0.6:
        factor = (lat - 0.6) / 0.4
        for cold in ("tundra", "frozen_tundra"):
            weights[cold] = weights.get(cold, 0.0) * (1.0 + 4.0 * factor)
        for warm in ("jungle", "desert", "deep_desert"):
            weights[warm] = weights.get(warm, 0.0) * (1.0 - 0.8 * factor)


# ---------------------------------------------------------------------------
# Voronoi terrain expansion
# ---------------------------------------------------------------------------

def _voronoi_assign(
    terrain_str: dict[tuple[int, int], str],
    seed_positions: list[tuple[int, int]],
    land_tiles: list[tuple[int, int]],
    rng: random.Random,
) -> None:
    """Assign each unassigned land tile to the nearest seed's terrain.

    Gaussian jitter on the distance metric makes boundaries irregular.
    """
    if not seed_positions:
        return
    for (x, y) in land_tiles:
        if terrain_str[(x, y)] != "":
            continue
        best_d2 = float("inf")
        best_t  = "plain"
        for sx, sy in seed_positions:
            jitter = rng.gauss(0, 2.5) ** 2
            d2 = (x - sx) ** 2 + (y - sy) ** 2 + jitter
            if d2 < best_d2:
                best_d2 = d2
                best_t  = terrain_str[(sx, sy)]
        terrain_str[(x, y)] = best_t


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


# ---------------------------------------------------------------------------
# Rivers (marks is_river, keeps underlying terrain/modifier/move_cost)
# ---------------------------------------------------------------------------

def _add_rivers(
    tiles: list[Tile],
    elev: dict[tuple[int, int], float],
    width: int,
    height: int,
    seed: int,
) -> None:
    rp      = config.river_params()
    penalty = config.river_movement_penalty()
    rng     = random.Random(seed + 42)
    grid    = {(t.x, t.y): t for t in tiles}
    num_rivers  = max(1, (width * height) // int(rp["count_divisor"]))
    min_descent = rp["min_descent"]

    for _ in range(num_rivers):
        high_tiles = [
            t for t in tiles
            if t.modifier in (ModifierType.HILLS, ModifierType.MOUNTAIN)
            and t.terrain not in (
                TerrainType.OCEAN, TerrainType.COASTAL,
                TerrainType.CLIFF_COAST, TerrainType.FLOODPLAIN,
            )
        ]
        if not high_tiles:
            break
        start = rng.choice(high_tiles)
        cx, cy = start.x, start.y

        for _ in range((width + height) * 2):
            current = grid.get((cx, cy))
            if current is None:
                break
            if current.terrain in (
                TerrainType.OCEAN, TerrainType.COASTAL,
                TerrainType.CLIFF_COAST, TerrainType.FLOODPLAIN,
            ):
                break
            if not current.is_river:
                current.is_river = True
                # Add river movement penalty on top of existing terrain cost
                if current.move_cost is not None:
                    current.move_cost = current.move_cost + penalty

            neighbors = [
                grid.get((cx + dx, cy + dy))
                for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]
            ]
            valid = [n for n in neighbors if n is not None]
            if not valid:
                break
            nxt = min(valid, key=lambda t: elev[(t.x, t.y)])
            if elev[(nxt.x, nxt.y)] >= (elev[(cx, cy)] - min_descent):
                break
            cx, cy = nxt.x, nxt.y


# ---------------------------------------------------------------------------
# Inland coastal fix — coastal types must be ≤ 2 tiles from ocean
# ---------------------------------------------------------------------------

def _fix_inland_coastal(tiles: list[Tile], rng: random.Random) -> None:
    """Convert coastal-type tiles that are >2 Manhattan tiles from any ocean."""
    grid = {(t.x, t.y): t for t in tiles}
    ocean_set = {(t.x, t.y) for t in tiles if t.terrain == TerrainType.OCEAN}
    coastal_types = {TerrainType.COASTAL, TerrainType.FLOODPLAIN, TerrainType.CLIFF_COAST}

    for tile in tiles:
        if tile.terrain not in coastal_types:
            continue
        # Check Manhattan distance ≤ 2 to any ocean tile
        near_ocean = any(
            abs(tile.x - ox) + abs(tile.y - oy) <= 2
            for ox, oy in ocean_set
        )
        if near_ocean:
            continue
        # Convert to the most common adjacent land terrain, or plain as fallback
        nbr_terrains = []
        for dx, dy in [(-1,0),(1,0),(0,-1),(0,1),(-1,-1),(1,-1),(-1,1),(1,1)]:
            nbr = grid.get((tile.x + dx, tile.y + dy))
            if nbr and nbr.terrain not in coastal_types and nbr.terrain != TerrainType.OCEAN:
                nbr_terrains.append(nbr.terrain)
        new_terrain = rng.choice(nbr_terrains) if nbr_terrains else TerrainType.PLAIN
        tile.terrain   = new_terrain
        tile.move_cost = config.get_move_cost(new_terrain.value, tile.modifier.value)


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
