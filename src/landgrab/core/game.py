"""Core game logic: create, save, load, and advance game state."""

from __future__ import annotations

import heapq
import json
import random
import uuid
from datetime import UTC, datetime
from pathlib import Path

from landgrab.core import config
from landgrab.core.dice import roll
from landgrab.core.map_gen import generate_map
from landgrab.models.game_state import (
    EndTurnResult,
    GameState,
    ModifierType,
    MoveResult,
    MoveToResult,
    Player,
    RollResult,
    SavedGame,
    TerrainType,
    TurnPhase,
    WorldSettings,
    tile_map,
)

SAVES_DIR = Path("saves")

_TERRAIN_MESSAGES: dict[TerrainType, str] = {
    TerrainType.COASTAL:      "You reach the rocky coastline.",
    TerrainType.FLOODPLAIN:   "You wade through the low floodplains.",
    TerrainType.CLIFF_COAST:  "You clamber along the cliff coast.",
    TerrainType.PLAIN:        "You stride across open plains.",
    TerrainType.GRASSLAND:    "You walk through rolling grasslands.",
    TerrainType.FOREST:       "You push through dense woodland.",
    TerrainType.THICK_FOREST: "You hack through thick forest.",
    TerrainType.JUNGLE:       "You struggle through the jungle undergrowth.",
    TerrainType.MARSH:        "You squelch across the marshy ground.",
    TerrainType.DESERT:       "You trudge through the sandy desert.",
    TerrainType.DEEP_DESERT:  "You battle the relentless deep desert.",
    TerrainType.TUNDRA:       "You crunch across frozen tundra.",
    TerrainType.FROZEN_TUNDRA:"You struggle through the frozen wasteland.",
    TerrainType.RIVER:        "You ford the rushing river.",
}

_MODIFIER_MESSAGES: dict[ModifierType, str] = {
    ModifierType.FLAT:     "",
    ModifierType.HILLS:    " The hills slow your march.",
    ModifierType.MOUNTAIN: " You struggle up the steep mountain slopes.",
}


def new_game(
    player_name: str,
    width: int,
    height: int,
    seed: int | None,
    world: WorldSettings | None = None,
) -> GameState:
    game_id = str(uuid.uuid4())[:8]
    resolved_seed = seed if seed is not None else random.randint(0, 2**31)
    resolved_world = world or WorldSettings()
    tiles = generate_map(width, height, resolved_seed, resolved_world)

    cx, cy = width // 2, height // 2
    spawn = _find_spawn(tiles, cx, cy)

    player = Player(id=str(uuid.uuid4())[:8], name=player_name, position=spawn)
    state = GameState(
        game_id=game_id,
        player=player,
        map_width=width,
        map_height=height,
        tiles=tiles,
        phase=TurnPhase.ROLL,
        seed=resolved_seed,
        world=resolved_world,
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
            mtime = datetime.fromtimestamp(f.stat().st_mtime, tz=UTC).isoformat()
            saves.append(SavedGame(
                game_id=state.game_id,
                player_name=state.player.name,
                turn=state.turn,
                saved_at=mtime,
            ))
        except Exception:
            continue
    return saves


def roll_for_turn(game_id: str) -> RollResult:
    state = load_game(game_id)
    if state.phase != TurnPhase.ROLL:
        raise ValueError("Already rolled this turn.")

    d = roll()
    state.player.movement_total = d
    state.player.movement_remaining = d
    state.phase = TurnPhase.MOVE
    _save(state)

    return RollResult(
        roll=d,
        movement_total=d,
        message=f"You rolled a {d}! {d} movement points this turn.",
        game_state=state,
    )


def move(game_id: str, dx: int, dy: int) -> MoveResult:
    state = load_game(game_id)
    tmap = tile_map(state)

    if state.phase != TurnPhase.MOVE:
        raise ValueError("Roll the dice before moving.")
    if state.player.movement_remaining <= 0:
        raise ValueError("No movement points remaining. End your turn.")

    px, py = state.player.position
    nx = max(0, min(state.map_width - 1, px + dx))
    ny = max(0, min(state.map_height - 1, py + dy))

    if dx == 0 and dy == 0:
        cur = tmap[(px, py)]
        return MoveResult(
            new_position=(px, py),
            terrain=cur.terrain,
            modifier=cur.modifier,
            move_cost=0,
            movement_remaining=state.player.movement_remaining,
            message="You hold your position.",
            game_state=state,
        )

    target = tmap.get((nx, ny))
    cost   = target.move_cost if target else None

    if target is None or cost is None:
        label = (
            "The ocean blocks your path."
            if (target and target.terrain == TerrainType.OCEAN)
            else "Edge of the world."
        )
        cur = tmap[(px, py)]
        return MoveResult(
            new_position=(px, py),
            terrain=cur.terrain,
            modifier=cur.modifier,
            move_cost=0,
            movement_remaining=state.player.movement_remaining,
            message=label,
            game_state=state,
        )

    if cost > state.player.movement_remaining:
        cur = tmap[(px, py)]
        return MoveResult(
            new_position=(px, py),
            terrain=cur.terrain,
            modifier=cur.modifier,
            move_cost=0,
            movement_remaining=state.player.movement_remaining,
            message=(
                f"Not enough movement. {target.terrain.value.title()} "
                f"({target.modifier.value}) costs {cost}, "
                f"you have {state.player.movement_remaining} left."
            ),
            game_state=state,
        )

    state.player.position = (nx, ny)
    state.player.movement_remaining -= cost
    _save(state)

    flavor = _TERRAIN_MESSAGES.get(target.terrain, "You move forward.")
    mod_msg = _MODIFIER_MESSAGES.get(target.modifier, "")
    msg = f"{flavor}{mod_msg} (cost: {cost} · remaining: {state.player.movement_remaining})"

    return MoveResult(
        new_position=(nx, ny),
        terrain=target.terrain,
        modifier=target.modifier,
        move_cost=cost,
        movement_remaining=state.player.movement_remaining,
        message=msg,
        game_state=state,
    )


def move_to(game_id: str, tx: int, ty: int) -> MoveToResult:
    """Move player to (tx, ty) via Dijkstra shortest path, spending MP."""
    state = load_game(game_id)
    tmap  = tile_map(state)

    if state.phase != TurnPhase.MOVE:
        raise ValueError("Roll the dice before moving.")
    if state.player.movement_remaining <= 0:
        raise ValueError("No movement points remaining. End your turn.")

    px, py = state.player.position
    if (tx, ty) == (px, py):
        raise ValueError("Already there.")

    path, total_cost = _dijkstra(tmap, px, py, tx, ty, state.map_width, state.map_height)
    if path is None:
        raise ValueError("No passable path to that tile.")
    if total_cost > state.player.movement_remaining:
        raise ValueError(
            f"Path costs {total_cost} MP but you only have {state.player.movement_remaining}."
        )

    state.player.position = (tx, ty)
    state.player.movement_remaining -= total_cost
    _save(state)

    target = tmap[(tx, ty)]
    flavor = _TERRAIN_MESSAGES.get(target.terrain, "You arrive.")
    mod_msg = _MODIFIER_MESSAGES.get(target.modifier, "")
    msg = f"{flavor}{mod_msg} (cost: {total_cost} · remaining: {state.player.movement_remaining})"

    return MoveToResult(
        new_position=(tx, ty),
        terrain=target.terrain,
        modifier=target.modifier,
        total_cost=total_cost,
        movement_remaining=state.player.movement_remaining,
        path=path,
        message=msg,
        game_state=state,
    )


def _dijkstra(
    tmap: dict[tuple[int, int], object],
    sx: int, sy: int,
    tx: int, ty: int,
    width: int, height: int,
) -> tuple[list[tuple[int, int]] | None, int]:
    """Dijkstra with diagonal cost formula from terrain.config.

    Cardinal: cost = destination.move_cost
    Diagonal: cost = round(a/2 + (b/2) * sqrt(b))
              where a = origin.move_cost, b = destination.move_cost
    """
    from landgrab.core.config import die_sides
    _die = die_sides()

    dist: dict[tuple[int, int], int] = {(sx, sy): 0}
    prev: dict[tuple[int, int], tuple[int, int] | None] = {(sx, sy): None}
    heap: list[tuple[int, int, int]] = [(0, sx, sy)]

    while heap:
        cost, x, y = heapq.heappop(heap)
        if (x, y) == (tx, ty):
            break
        if cost > dist.get((x, y), 10**9):
            continue
        origin_tile = tmap.get((x, y))
        origin_cost = getattr(origin_tile, "move_cost", None) or 1
        for dx, dy in [(-1,0),(1,0),(0,-1),(0,1),(-1,-1),(1,-1),(-1,1),(1,1)]:
            nx, ny = x + dx, y + dy
            if not (0 <= nx < width and 0 <= ny < height):
                continue
            tile = tmap.get((nx, ny))
            if tile is None:
                continue
            b = getattr(tile, "move_cost", None)
            if b is None:
                continue
            if dx != 0 and dy != 0:  # diagonal
                step_cost = round(origin_cost / 2 + (b / 2) * (b ** 0.5))
            else:
                step_cost = b
            if step_cost >= _die:  # treat ≥ die ceiling as impassable
                continue
            new_cost = cost + step_cost
            if new_cost < dist.get((nx, ny), 10**9):
                dist[(nx, ny)] = new_cost
                prev[(nx, ny)] = (x, y)
                heapq.heappush(heap, (new_cost, nx, ny))

    if (tx, ty) not in prev:
        return None, 0

    path: list[tuple[int, int]] = []
    cur: tuple[int, int] | None = (tx, ty)
    while cur is not None:
        path.append(cur)
        cur = prev[cur]
    path.reverse()
    return path, dist[(tx, ty)]


def end_turn(game_id: str) -> EndTurnResult:
    state = load_game(game_id)
    state.turn += 1
    state.phase = TurnPhase.ROLL
    state.player.movement_remaining = 0
    state.player.movement_total = 0
    _save(state)

    return EndTurnResult(
        turn=state.turn,
        message=f"Turn {state.turn} begins. Roll the dice!",
        game_state=state,
    )


# ── helpers ───────────────────────────────────────────────────────────────────

def _find_spawn(tiles: list, cx: int, cy: int) -> tuple[int, int]:
    spawn_cfg = config.spawn_params()
    invalid   = set(spawn_cfg["invalid_terrains"])
    preferred = set(spawn_cfg["preferred_terrains"])

    # Try preferred first, closest to center
    preferred_tiles = sorted(
        [t for t in tiles if t.terrain.value not in invalid and t.terrain.value in preferred],
        key=lambda t: abs(t.x - cx) + abs(t.y - cy),
    )
    if preferred_tiles:
        return (preferred_tiles[0].x, preferred_tiles[0].y)

    # Fallback: any valid tile
    valid_tiles = sorted(
        [t for t in tiles if t.terrain.value not in invalid],
        key=lambda t: abs(t.x - cx) + abs(t.y - cy),
    )
    if valid_tiles:
        return (valid_tiles[0].x, valid_tiles[0].y)

    return (cx, cy)


def _save_path(game_id: str) -> Path:
    SAVES_DIR.mkdir(exist_ok=True)
    return SAVES_DIR / f"{game_id}.json"


def _save(state: GameState) -> None:
    _save_path(state.game_id).write_text(state.model_dump_json(indent=2))
