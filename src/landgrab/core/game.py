"""Core game logic: create, save, load, and advance game state."""

from __future__ import annotations

import heapq
import json
import random
import uuid
from datetime import datetime, timezone
from pathlib import Path

from landgrab.core.dice import roll
from landgrab.core.map_gen import generate_map
from landgrab.models.game_state import (
    EndTurnResult,
    GameState,
    MoveResult,
    MoveToResult,
    Player,
    RollResult,
    SavedGame,
    TERRAIN_MOVE_COST,
    TerrainType,
    TurnPhase,
    tile_map,
)

SAVES_DIR = Path("saves")

_TERRAIN_MESSAGES: dict[TerrainType, str] = {
    TerrainType.COAST:     "You reach the rocky coastline.",
    TerrainType.PLAINS:    "You stride across open plains.",
    TerrainType.FOREST:    "You push through dense woodland.",
    TerrainType.HILLS:     "You climb the rolling hills.",
    TerrainType.MOUNTAINS: "You struggle up the steep mountain slopes.",
    TerrainType.RIVER:     "You ford the rushing river.",
}


def new_game(player_name: str, width: int, height: int, seed: int | None) -> GameState:
    game_id = str(uuid.uuid4())[:8]
    resolved_seed = seed if seed is not None else random.randint(0, 2**31)
    tiles = generate_map(width, height, resolved_seed)

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


def roll_for_turn(game_id: str) -> RollResult:
    state = load_game(game_id)
    if state.phase != TurnPhase.ROLL:
        raise ValueError("Already rolled this turn.")

    d8 = roll(8)
    state.player.movement_total = d8
    state.player.movement_remaining = d8
    state.phase = TurnPhase.MOVE
    _save(state)

    return RollResult(
        roll=d8,
        movement_total=d8,
        message=f"You rolled a {d8}! {d8} movement points this turn.",
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

    # No-op wait move
    if dx == 0 and dy == 0:
        return MoveResult(
            new_position=(px, py),
            terrain=tmap[(px, py)].terrain,
            move_cost=0,
            movement_remaining=state.player.movement_remaining,
            message="You hold your position.",
            game_state=state,
        )

    target = tmap.get((nx, ny))
    cost = TERRAIN_MOVE_COST.get(target.terrain) if target else None

    if target is None or cost is None:
        label = "The ocean blocks your path." if (target and target.terrain == TerrainType.OCEAN) else "Edge of the world."
        return MoveResult(
            new_position=(px, py),
            terrain=tmap[(px, py)].terrain,
            move_cost=0,
            movement_remaining=state.player.movement_remaining,
            message=label,
            game_state=state,
        )

    if cost > state.player.movement_remaining:
        return MoveResult(
            new_position=(px, py),
            terrain=tmap[(px, py)].terrain,
            move_cost=0,
            movement_remaining=state.player.movement_remaining,
            message=f"Not enough movement. {target.terrain.value.title()} costs {cost}, you have {state.player.movement_remaining} left.",
            game_state=state,
        )

    state.player.position = (nx, ny)
    state.player.movement_remaining -= cost
    _save(state)

    terrain = target.terrain
    remaining = state.player.movement_remaining
    flavor = _TERRAIN_MESSAGES.get(terrain, "You move forward.")
    msg = f"{flavor} (cost: {cost} · remaining: {remaining})"

    return MoveResult(
        new_position=(nx, ny),
        terrain=terrain,
        move_cost=cost,
        movement_remaining=remaining,
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

    terrain = tmap[(tx, ty)].terrain
    remaining = state.player.movement_remaining
    flavor = _TERRAIN_MESSAGES.get(terrain, "You arrive.")
    msg = f"{flavor} (cost: {total_cost} · remaining: {remaining})"

    return MoveToResult(
        new_position=(tx, ty),
        terrain=terrain,
        total_cost=total_cost,
        movement_remaining=remaining,
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
    """Return (path, cost) from (sx,sy) to (tx,ty), or (None, 0) if unreachable."""
    dist: dict[tuple[int, int], int] = {(sx, sy): 0}
    prev: dict[tuple[int, int], tuple[int, int] | None] = {(sx, sy): None}
    heap: list[tuple[int, int, int]] = [(0, sx, sy)]

    while heap:
        cost, x, y = heapq.heappop(heap)
        if (x, y) == (tx, ty):
            break
        if cost > dist.get((x, y), 10**9):
            continue
        for dx, dy in [(-1,0),(1,0),(0,-1),(0,1),(-1,-1),(1,-1),(-1,1),(1,1)]:
            nx, ny = x + dx, y + dy
            if not (0 <= nx < width and 0 <= ny < height):
                continue
            tile = tmap.get((nx, ny))
            if tile is None:
                continue
            step_cost = TERRAIN_MOVE_COST.get(tile.terrain)  # type: ignore[arg-type]
            if step_cost is None:
                continue  # impassable
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
    preferred = {TerrainType.PLAINS, TerrainType.COAST}
    by_dist = sorted(
        [t for t in tiles if t.terrain in preferred],
        key=lambda t: abs(t.x - cx) + abs(t.y - cy),
    )
    if by_dist:
        return (by_dist[0].x, by_dist[0].y)
    return (cx, cy)


def _save_path(game_id: str) -> Path:
    SAVES_DIR.mkdir(exist_ok=True)
    return SAVES_DIR / f"{game_id}.json"


def _save(state: GameState) -> None:
    _save_path(state.game_id).write_text(state.model_dump_json(indent=2))
