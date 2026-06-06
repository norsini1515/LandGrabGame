"""Procedural map generation using layered OpenSimplex noise."""

from __future__ import annotations

import random

try:
    import opensimplex  # type: ignore[import]
    _HAS_NOISE = True
except ImportError:
    _HAS_NOISE = False

from landgrab.models.game_state import TerrainType, Tile


# Elevation thresholds
_OCEAN_MAX     = 0.30
_COAST_MAX     = 0.38
_PLAINS_MAX    = 0.55
_FOREST_MAX    = 0.68
_HILLS_MAX     = 0.80


def _elevation_to_terrain(e: float) -> TerrainType:
    if e < _OCEAN_MAX:     return TerrainType.OCEAN
    if e < _COAST_MAX:     return TerrainType.COAST
    if e < _PLAINS_MAX:    return TerrainType.PLAINS
    if e < _FOREST_MAX:    return TerrainType.FOREST
    if e < _HILLS_MAX:     return TerrainType.HILLS
    return TerrainType.MOUNTAINS


def _noise_elevation(x: int, y: int, width: int, height: int, seed: int) -> float:
    if not _HAS_NOISE:
        rng = random.Random(seed ^ (x * 73856093) ^ (y * 19349663))
        base = rng.random()
    else:
        opensimplex.seed(seed)
        scale = 0.06
        value = amplitude = frequency = 0.0
        amplitude = 1.0
        frequency = 1.0
        max_value = 0.0
        for _ in range(6):
            value     += opensimplex.noise2(x * scale * frequency, y * scale * frequency) * amplitude
            max_value += amplitude
            amplitude *= 0.5
            frequency *= 2.0
        base = (value / max_value + 1.0) / 2.0

    edge_fade = _edge_fade(x, y, width, height)
    return base * edge_fade


def _edge_fade(x: int, y: int, width: int, height: int) -> float:
    dx = abs(x / width  - 0.5) * 2
    dy = abs(y / height - 0.5) * 2
    dist = max(dx, dy)
    fade_start = 0.6
    if dist < fade_start:
        return 1.0
    t = (dist - fade_start) / (1.0 - fade_start)
    return max(0.0, 1.0 - t * t)


def generate_map(width: int, height: int, seed: int) -> list[Tile]:
    tiles: list[Tile] = []
    for y in range(height):
        for x in range(width):
            elevation = _noise_elevation(x, y, width, height, seed)
            terrain = _elevation_to_terrain(elevation)
            tiles.append(Tile(x=x, y=y, terrain=terrain, elevation=round(elevation, 4)))

    _add_rivers(tiles, width, height, seed)
    _fix_interior_ocean(tiles)
    return tiles


def _fix_interior_ocean(tiles: list[Tile]) -> None:
    """Convert ocean tiles that touch any land tile to coast (inland seas → coast)."""
    grid: dict[tuple[int, int], Tile] = {(t.x, t.y): t for t in tiles}
    land = {TerrainType.PLAINS, TerrainType.FOREST, TerrainType.HILLS,
            TerrainType.MOUNTAINS, TerrainType.COAST, TerrainType.RIVER}
    for tile in tiles:
        if tile.terrain != TerrainType.OCEAN:
            continue
        for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            neighbor = grid.get((tile.x + dx, tile.y + dy))
            if neighbor and neighbor.terrain in land:
                tile.terrain = TerrainType.COAST
                break


def _add_rivers(tiles: list[Tile], width: int, height: int, seed: int) -> None:
    grid: dict[tuple[int, int], Tile] = {(t.x, t.y): t for t in tiles}
    rng = random.Random(seed + 42)
    num_rivers = max(1, (width * height) // 400)

    for _ in range(num_rivers):
        hill_tiles = [t for t in tiles if t.terrain in (TerrainType.HILLS, TerrainType.MOUNTAINS)]
        if not hill_tiles:
            break
        start = rng.choice(hill_tiles)
        cx, cy = start.x, start.y

        for _ in range(width + height):
            current = grid.get((cx, cy))
            if current is None:
                break
            if current.terrain in (TerrainType.OCEAN, TerrainType.COAST):
                break
            if current.terrain != TerrainType.MOUNTAINS:
                current.terrain = TerrainType.RIVER

            neighbors = [grid.get((cx + dx, cy + dy)) for dx, dy in [(-1,0),(1,0),(0,-1),(0,1)]]
            valid = [n for n in neighbors if n is not None]
            if not valid:
                break
            nxt = min(valid, key=lambda t: t.elevation)
            if nxt.elevation >= (current.elevation - 0.005):
                break
            cx, cy = nxt.x, nxt.y
