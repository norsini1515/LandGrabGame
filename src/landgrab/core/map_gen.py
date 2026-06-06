"""Procedural map generation using layered OpenSimplex noise."""

from __future__ import annotations

import random

try:
    import opensimplex  # type: ignore[import]
    _HAS_NOISE = True
except ImportError:
    _HAS_NOISE = False

from landgrab.models.game_state import TerrainType, Tile


# Elevation thresholds — tweak to taste
_OCEAN_MAX = 0.30
_COAST_MAX = 0.38
_PLAINS_MAX = 0.55
_FOREST_MAX = 0.68
_HILLS_MAX = 0.80
_MOUNTAINS_MAX = 0.92
# anything above → peak (still mountains for now)


def _elevation_to_terrain(e: float) -> TerrainType:
    if e < _OCEAN_MAX:
        return TerrainType.OCEAN
    if e < _COAST_MAX:
        return TerrainType.COAST
    if e < _PLAINS_MAX:
        return TerrainType.PLAINS
    if e < _FOREST_MAX:
        return TerrainType.FOREST
    if e < _HILLS_MAX:
        return TerrainType.HILLS
    return TerrainType.MOUNTAINS


def _perlin_elevation(x: int, y: int, width: int, height: int, seed: int) -> float:
    """Return a [0, 1] elevation value for tile (x, y)."""
    if not _HAS_NOISE:
        # Fallback: simple deterministic pseudo-random with edge fade
        rng = random.Random(seed ^ (x * 73856093) ^ (y * 19349663))
        base = rng.random()
    else:
        # Layered octaves of OpenSimplex noise for a natural-looking heightmap
        opensimplex.seed(seed)
        scale = 0.06
        value = 0.0
        amplitude = 1.0
        frequency = 1.0
        max_value = 0.0
        for _ in range(6):  # 6 octaves
            value += opensimplex.noise2(x * scale * frequency, y * scale * frequency) * amplitude
            max_value += amplitude
            amplitude *= 0.5   # persistence
            frequency *= 2.0   # lacunarity
        # opensimplex returns [-1, 1] → normalize to [0, 1]
        base = (value / max_value + 1.0) / 2.0

    # Fade edges toward ocean to create a continent feel
    edge_fade = _edge_fade(x, y, width, height)
    return base * edge_fade


def _edge_fade(x: int, y: int, width: int, height: int) -> float:
    """Multiplier that pushes map edges toward 0 (ocean)."""
    nx = x / width
    ny = y / height
    # Distance from center, normalized
    dx = abs(nx - 0.5) * 2  # 0 at center, 1 at edge
    dy = abs(ny - 0.5) * 2
    dist = max(dx, dy)
    # Smooth falloff starting at 60% from center
    fade_start = 0.6
    if dist < fade_start:
        return 1.0
    t = (dist - fade_start) / (1.0 - fade_start)
    return max(0.0, 1.0 - t * t)


def generate_map(width: int, height: int, seed: int) -> list[Tile]:
    """Generate a list of Tiles for a width×height map."""
    tiles: list[Tile] = []
    for y in range(height):
        for x in range(width):
            elevation = _perlin_elevation(x, y, width, height, seed)
            terrain = _elevation_to_terrain(elevation)
            tiles.append(Tile(x=x, y=y, terrain=terrain, elevation=round(elevation, 4)))

    # Simple river pass: trace a few paths from high to low
    _add_rivers(tiles, width, height, seed)
    return tiles


def _add_rivers(tiles: list[Tile], width: int, height: int, seed: int) -> None:
    """Overwrite some hill/forest tiles along descent paths with RIVER terrain."""
    tile_grid: dict[tuple[int, int], Tile] = {(t.x, t.y): t for t in tiles}
    rng = random.Random(seed + 42)
    num_rivers = max(1, (width * height) // 400)

    for _ in range(num_rivers):
        # Start from a random hills/mountains tile
        hill_tiles = [
            t for t in tiles
            if t.terrain in (TerrainType.HILLS, TerrainType.MOUNTAINS)
        ]
        if not hill_tiles:
            break
        start = rng.choice(hill_tiles)
        cx, cy = start.x, start.y

        for _step in range(width + height):
            current = tile_grid.get((cx, cy))
            if current is None:
                break
            if current.terrain in (TerrainType.OCEAN, TerrainType.COAST):
                break
            # Mark as river (only inland tiles)
            if current.terrain not in (TerrainType.MOUNTAINS,):
                current.terrain = TerrainType.RIVER

            # Move to lowest neighbor
            neighbors = [
                tile_grid.get((cx + dx, cy + dy))
                for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]
            ]
            valid = [n for n in neighbors if n is not None]
            if not valid:
                break
            nxt = min(valid, key=lambda t: t.elevation)
            if nxt.elevation >= (current.elevation - 0.005):
                break  # stuck on a plateau — stop
            cx, cy = nxt.x, nxt.y
