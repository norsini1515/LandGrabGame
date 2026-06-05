"""Core game logic: create, save, load, and advance game state."""

from __future__ import annotations

import json
import random
import uuid
from datetime import datetime, timezone
from pathlib import Path

from landgrab.core.dice import roll
from landgrab.core.map_gen import generate_map
from landgrab.models.game_state import (
    GameState,
    MoveResult,
    Player,
    SavedGame,
    TerrainType,
    tile_map,
)

SAVES_DIR = Path("saves")

_TERRAIN_MESSAGES: dict[TerrainType, str] = {
    TerrainType.OCEAN: "You wade into the open sea — impassable.",
    TerrainType.COAST: "You reach the rocky coastline.",
    TerrainType.PLAINS: "You stride across open plains.",
    TerrainType.FOREST: "You push through dense woodland.",
    TerrainType.HILLS: "You climb the rolling hills.",
    TerrainType.MOUNTAINS: "You struggle up the steep mountain slopes.",
    TerrainType.RIVER: "You ford the rushing river.",
}


def new_game(player_name: str, width: int, height: int, seed: int | None) -> GameState:
    game_id = str(uuid.uuid4())[:8]
    resolved_seed = seed if seed is not None else random.randint(0, 2**31)
    tiles = generate_map(width, height, resolved_seed)

    # Spawn player on the first plains tile near the center
    cx, cy = width // 2, height // 2
    spawn = _find_spawn(tiles, cx, cy, width, height)

    player = Player(id=str(uuid.uuid4())[:8], name=player_name, position=spawn)
    state = GameState(
        game_id=game_id,
        player=player,
        map_width=width,
        map_height=height,
        tiles=tiles,
        seed=resolved_seed,
    )
    _save(state)
    return state


def load_game(game_id: str) -> GameState:
    path = _save_path(game_id)
    if not path.exists():
        raise FileNotFoundError(f"No save found for game_id={game_id!r}")
    data = json.loads(path.read_text())
    return GameState.model_validate(data)


def list_saves() -> list[SavedGame]:
    SAVES_DIR.mkdir(exist_ok=True)
    saves: list[SavedGame] = []
    for f in sorted(SAVES_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            data = json.loads(f.read_text())
            state = GameState.model_validate(data)
            mtime = datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc).isoformat()
            saves.append(SavedGame(
                game_id=state.game_id,
                player_name=state.player.name,
                turn=state.turn,
                saved_at=mtime,
            ))
        except Exception:
            continue
    return saves


def move(game_id: str, dx: int, dy: int) -> MoveResult:
    state = load_game(game_id)
    tmap = tile_map(state)

    d8 = roll(8)
    px, py = state.player.position
    nx = max(0, min(state.map_width - 1, px + dx))
    ny = max(0, min(state.map_height - 1, py + dy))

    target = tmap.get((nx, ny))
    if target is None or target.terrain == TerrainType.OCEAN:
        msg = "The ocean blocks your path." if target else "Edge of the world."
        return MoveResult(
            new_position=(px, py),
            roll=d8,
            terrain=tmap[(px, py)].terrain,
            message=msg,
            game_state=state,
        )

    state.player.position = (nx, ny)
    state.turn += 1
    _save(state)

    terrain = target.terrain
    msg = f"(d8 → {d8}) " + _TERRAIN_MESSAGES.get(terrain, "You move forward.")
    return MoveResult(
        new_position=(nx, ny),
        roll=d8,
        terrain=terrain,
        message=msg,
        game_state=state,
    )


# ── helpers ──────────────────────────────────────────────────────────────────

def _find_spawn(tiles: list, cx: int, cy: int, width: int, height: int) -> tuple[int, int]:
    """Return the nearest plains/coast tile to (cx, cy) as spawn point."""
    preferred = {TerrainType.PLAINS, TerrainType.COAST}
    by_dist = sorted(
        [t for t in tiles if t.terrain in preferred],
        key=lambda t: abs(t.x - cx) + abs(t.y - cy),
    )
    if by_dist:
        t = by_dist[0]
        return (t.x, t.y)
    return (cx, cy)


def _save_path(game_id: str) -> Path:
    SAVES_DIR.mkdir(exist_ok=True)
    return SAVES_DIR / f"{game_id}.json"


def _save(state: GameState) -> None:
    _save_path(state.game_id).write_text(state.model_dump_json(indent=2))
