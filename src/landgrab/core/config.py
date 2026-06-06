"""Parse terrain.config and map_gen.config into typed accessors."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

_SRC = Path(__file__).parent.parent.parent  # src/

_TERRAIN_CONFIG = _SRC / "terrain.config"
_MAP_GEN_CONFIG = _SRC / "map_gen.config"


# ---------------------------------------------------------------------------
# Raw parser
# ---------------------------------------------------------------------------

def _parse(path: Path) -> dict[str, dict[str, str]]:
    """Parse a .config file into {section: {key: raw_value}}."""
    sections: dict[str, dict[str, str]] = {}
    current: dict[str, str] = {}
    section_name = ""

    for raw in path.read_text().splitlines():
        line = raw.split("#")[0].strip()
        if not line:
            continue
        if line.startswith("[") and line.endswith("]"):
            section_name = line[1:-1].strip()
            current = sections.setdefault(section_name, {})
            continue
        if "=" in line:
            key, _, val = line.partition("=")
            current[key.strip()] = val.strip()

    return sections


@lru_cache(maxsize=1)
def _terrain() -> dict[str, dict[str, str]]:
    return _parse(_TERRAIN_CONFIG)


@lru_cache(maxsize=1)
def _mapgen() -> dict[str, dict[str, str]]:
    return _parse(_MAP_GEN_CONFIG)


def _float(sections: dict[str, dict[str, str]], sec: str, key: str) -> float:
    return float(sections[sec][key])


def _int(sections: dict[str, dict[str, str]], sec: str, key: str) -> int:
    return int(sections[sec][key])


def _str(sections: dict[str, dict[str, str]], sec: str, key: str) -> str:
    return sections[sec][key]


def _csv_floats(val: str) -> list[float]:
    return [float(x.strip()) for x in val.split(",") if x.strip()]


def _csv_strs(val: str) -> list[str]:
    return [x.strip() for x in val.split(",") if x.strip()]


# ---------------------------------------------------------------------------
# terrain.config accessors
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def die_sides() -> int:
    return _int(_terrain(), "constants", "die")


@lru_cache(maxsize=1)
def combination_tuning_c() -> int:
    return _int(_terrain(), "constants", "combination_tuning_c")


@lru_cache(maxsize=1)
def terrain_base_costs() -> dict[str, int | None]:
    """Base movement cost per terrain string key, or None if impassable."""
    tc = _terrain()
    costs: dict[str, int | None] = {}
    for sec, vals in tc.items():
        if sec.startswith("terrain.") and "cost" in vals:
            name = sec[len("terrain."):]
            costs[name] = int(vals["cost"])
    # ocean is always impassable (not listed as a terrain section, handled separately)
    costs.setdefault("ocean", None)
    return costs


@lru_cache(maxsize=1)
def combination_costs() -> dict[str, dict[str, int]]:
    """combination_costs()[dominant][modifier] = total move cost."""
    tc = _terrain()
    result: dict[str, dict[str, int]] = {}
    for sec, vals in tc.items():
        if sec.startswith("combination."):
            dom = sec[len("combination."):]
            result[dom] = {k: int(v) for k, v in vals.items()}
    return result


def get_move_cost(terrain: str, modifier: str = "flat") -> int | None:
    """Return movement cost for a terrain+modifier combo, or None if impassable."""
    if terrain == "ocean":
        return None
    if modifier == "flat":
        return terrain_base_costs().get(terrain)
    # hills or mountain modifier — look up combination table
    combos = combination_costs()
    dom_table = combos.get(modifier)
    if dom_table and terrain in dom_table:
        cost = dom_table[terrain]
        # frozen_tundra+mountain=8 = die ceiling, treat as impassable
        if cost >= die_sides():
            return None
        return cost
    # fallback to base cost if combination not found
    return terrain_base_costs().get(terrain)


@lru_cache(maxsize=1)
def hills_thresholds() -> dict[str, float]:
    tc = _terrain()
    return {
        "flat":     _float(tc, "hills.thresholds", "hills_flat_threshold"),
        "mountain": _float(tc, "hills.thresholds", "hills_mountain_threshold"),
    }


@lru_cache(maxsize=1)
def hills_weights() -> dict[str, float]:
    tc = _terrain()
    sec = tc["hills.weights"]
    return {
        "alpha": float(sec["alpha"]),
        "beta":  float(sec["beta"]),
        "gamma": float(sec["gamma"]),
    }


@lru_cache(maxsize=1)
def hills_ranges() -> dict[str, tuple[float, float]]:
    tc = _terrain()
    sec = tc.get("hills.ranges", {})
    result: dict[str, tuple[float, float]] = {}
    for k, v in sec.items():
        parts = _csv_floats(v)
        if len(parts) == 2:
            result[k] = (parts[0], parts[1])
    return result


@lru_cache(maxsize=1)
def adjacency_matrix() -> dict[str, dict[str, float]]:
    """adjacency_matrix()[column_terrain][row_terrain] = probability (0-100)."""
    tc = _terrain()
    sec = tc.get("adjacency_matrix", {})

    # Column order from config header
    col_order = [
        "plain", "grassland", "forest", "thick_forest", "jungle", "marsh",
        "desert", "deep_desert", "tundra", "frozen_tundra", "coastal",
        "floodplain", "cliff_coast", "mountain",
    ]

    # Each key in the section is a row terrain name; value is comma-separated column probs
    rows: dict[str, list[float]] = {}
    for k, v in sec.items():
        row_terrain = k.lower()
        rows[row_terrain] = _csv_floats(v)

    # Build {col_terrain: {row_terrain: prob}}
    result: dict[str, dict[str, float]] = {c: {} for c in col_order}
    for row_name, probs in rows.items():
        for i, col in enumerate(col_order):
            if i < len(probs):
                result[col][row_name] = probs[i]

    return result


@lru_cache(maxsize=1)
def validity_matrix() -> dict[str, dict[str, bool]]:
    """validity_matrix()[terrain][modifier] = bool."""
    tc = _terrain()
    sec = tc.get("validity_matrix", {})
    result: dict[str, dict[str, bool]] = {}
    for k, v in sec.items():
        parts = _csv_floats(v)
        if len(parts) == 3:
            result[k] = {
                "flat":     bool(int(parts[0])),
                "hills":    bool(int(parts[1])),
                "mountain": bool(int(parts[2])),
        }
    return result


@lru_cache(maxsize=1)
def climate_multipliers() -> dict[str, dict[str, float]]:
    """climate_multipliers()[terrain][climate] = multiplier."""
    tc = _terrain()
    sec = tc.get("world.climate", {})
    result: dict[str, dict[str, float]] = {}
    climates = ["cold", "temperate", "hot"]
    for k, v in sec.items():
        if k in ("default", "options"):
            continue
        parts = _csv_floats(v)
        if len(parts) == 3:
            result[k] = dict(zip(climates, parts))
    return result


@lru_cache(maxsize=1)
def precipitation_multipliers() -> dict[str, dict[str, float]]:
    """precipitation_multipliers()[terrain][precip] = multiplier."""
    tc = _terrain()
    sec = tc.get("world.precipitation", {})
    result: dict[str, dict[str, float]] = {}
    precips = ["arid", "normal", "wet"]
    for k, v in sec.items():
        if k in ("default", "options"):
            continue
        parts = _csv_floats(v)
        if len(parts) == 3:
            result[k] = dict(zip(precips, parts))
    return result


@lru_cache(maxsize=1)
def world_defaults() -> dict[str, str]:
    tc = _terrain()
    return {
        "climate":        tc.get("world.climate", {}).get("default", "temperate"),
        "precipitation":  tc.get("world.precipitation", {}).get("default", "normal"),
        "age":            tc.get("world.age", {}).get("default", "old"),
        "fragmentation":  tc.get("world.fragmentation", {}).get("default", "default"),
    }


@lru_cache(maxsize=1)
def fragmentation_k() -> dict[str, float]:
    tc = _terrain()
    sec = tc.get("world.fragmentation", {})
    return {
        "continental": float(sec.get("continental", "0.5")),
        "default":     1.0,
        "fragmented":  float(sec.get("fragmented", "2.0")),
    }


@lru_cache(maxsize=1)
def age_hill_range_delta() -> dict[str, float]:
    tc = _terrain()
    sec = tc.get("world.age", {})
    return {
        "young": float(sec.get("hill_range_delta_young", "0.15")),
        "old":   float(sec.get("hill_range_delta_old", "-0.10")),
    }


@lru_cache(maxsize=1)
def map_size_defaults() -> dict[str, int]:
    tc = _terrain()
    sec = tc.get("map.size", {})
    return {
        "default_width":  int(sec.get("default_width",  "60")),
        "default_height": int(sec.get("default_height", "40")),
        "large_width":    int(sec.get("large_width",    "80")),
        "large_height":   int(sec.get("large_height",   "50")),
    }


@lru_cache(maxsize=1)
def seed_k_values() -> dict[str, float]:
    tc = _terrain()
    sec = tc.get("map.generation", {})
    return {
        "default": float(sec.get("seed_k_default", "1.0")),
        "min":     float(sec.get("seed_k_min",     "0.5")),
        "max":     float(sec.get("seed_k_max",     "2.0")),
    }


@lru_cache(maxsize=1)
def max_expansion_radius() -> int:
    tc = _terrain()
    sec = tc.get("map.generation", {})
    return int(sec.get("max_expansion_radius", "3"))


@lru_cache(maxsize=1)
def starting_position_config() -> dict[str, Any]:
    tc = _terrain()
    sec = tc.get("starting_positions", {})
    return {
        "mode":           sec.get("mode", "dispersed"),
        "min_distance":   int(sec.get("min_distance", "15")),
        "quality_radius": int(sec.get("quality_radius", "3")),
        "randomness":     float(sec.get("randomness", "0.2")),
    }


# ---------------------------------------------------------------------------
# map_gen.config accessors
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def noise_params() -> dict[str, float]:
    mg = _mapgen()
    sec = mg.get("noise", {})
    return {
        "scale":       float(sec.get("scale",       "0.06")),
        "octaves":     float(sec.get("octaves",     "6")),
        "persistence": float(sec.get("persistence", "0.5")),
        "lacunarity":  float(sec.get("lacunarity",  "2.0")),
    }


@lru_cache(maxsize=1)
def ocean_params() -> dict[str, float]:
    mg = _mapgen()
    sec = mg.get("ocean", {})
    return {
        "elevation_threshold":      float(sec.get("elevation_threshold",      "0.30")),
        "coastal_threshold":        float(sec.get("coastal_threshold",        "0.40")),
        "cliff_min_gradient":       float(sec.get("cliff_min_gradient",       "0.015")),
        "floodplain_max_gradient":  float(sec.get("floodplain_max_gradient",  "0.005")),
    }


@lru_cache(maxsize=1)
def edge_fade_start() -> float:
    mg = _mapgen()
    return float(mg.get("edge_fade", {}).get("start_ratio", "0.60"))


@lru_cache(maxsize=1)
def river_movement_penalty() -> int:
    tc = _terrain()
    return int(tc.get("map.river", {}).get("movement_penalty", "1"))


@lru_cache(maxsize=1)
def river_params() -> dict[str, float]:
    mg = _mapgen()
    sec = mg.get("rivers", {})
    return {
        "count_divisor": float(sec.get("count_divisor", "350")),
        "min_descent":   float(sec.get("min_descent",   "0.005")),
    }


@lru_cache(maxsize=1)
def spawn_params() -> dict[str, Any]:
    mg = _mapgen()
    sec = mg.get("spawn", {})
    return {
        "quality_radius":     int(sec.get("quality_radius", "3")),
        "preferred_terrains": _csv_strs(sec.get("preferred_terrains", "plain,grassland,coastal")),
        "invalid_terrains":   _csv_strs(
            sec.get("invalid_terrains", "ocean,river,cliff_coast,thick_forest")
        ),
    }


@lru_cache(maxsize=1)
def seed_expansion_max_fallback() -> int:
    mg = _mapgen()
    return int(mg.get("seed_expansion", {}).get("max_fallback_attempts", "50"))
