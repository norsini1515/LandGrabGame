"""Tests for map generation."""

from landgrab.core.map_gen import generate_map
from landgrab.models.game_state import ModifierType, TerrainType


def test_tile_count():
    tiles = generate_map(20, 15, seed=42)
    assert len(tiles) == 20 * 15


def test_all_positions_covered():
    w, h = 10, 10
    tiles = generate_map(w, h, seed=1)
    positions = {(t.x, t.y) for t in tiles}
    expected = {(x, y) for x in range(w) for y in range(h)}
    assert positions == expected


def test_edge_tiles_are_water():
    """Corner tiles should be ocean or coastal due to the edge fade."""
    w, h = 20, 20
    tiles = generate_map(w, h, seed=99)
    tile_map = {(t.x, t.y): t for t in tiles}
    corners = [(0, 0), (w-1, 0), (0, h-1), (w-1, h-1)]
    water = {
        TerrainType.OCEAN, TerrainType.COASTAL,
        TerrainType.FLOODPLAIN, TerrainType.CLIFF_COAST,
    }
    for pos in corners:
        assert tile_map[pos].terrain in water, (
            f"Corner {pos} is {tile_map[pos].terrain}, expected water"
        )


def test_elevation_in_range():
    tiles = generate_map(15, 15, seed=7)
    for t in tiles:
        assert 0.0 <= t.elevation <= 1.0


def test_deterministic():
    a = generate_map(10, 10, seed=12345)
    b = generate_map(10, 10, seed=12345)
    assert [(t.x, t.y, t.terrain, t.modifier) for t in a] == \
           [(t.x, t.y, t.terrain, t.modifier) for t in b]


def test_different_seeds_differ():
    a = generate_map(20, 20, seed=1)
    b = generate_map(20, 20, seed=2)
    terrains_a = [t.terrain for t in a]
    terrains_b = [t.terrain for t in b]
    assert terrains_a != terrains_b


def test_move_cost_set():
    """Every tile should have a move_cost (int or None for ocean)."""
    tiles = generate_map(15, 15, seed=5)
    for t in tiles:
        if t.terrain == TerrainType.OCEAN:
            assert t.move_cost is None
        else:
            assert t.move_cost is not None
            assert t.move_cost >= 1


def test_modifier_types_valid():
    tiles = generate_map(15, 15, seed=8)
    for t in tiles:
        assert isinstance(t.modifier, ModifierType)


def test_land_terrains_present():
    """A reasonably sized map should have several distinct land terrain types."""
    tiles = generate_map(40, 30, seed=42)
    land = {
        t.terrain for t in tiles
        if t.terrain not in (TerrainType.OCEAN, TerrainType.COASTAL,
                             TerrainType.FLOODPLAIN, TerrainType.CLIFF_COAST)
    }
    assert len(land) >= 3
