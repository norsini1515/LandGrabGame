"""Pydantic models for game state serialization."""

from __future__ import annotations

from enum import Enum
from pydantic import BaseModel, Field


class TerrainType(str, Enum):
    OCEAN = "ocean"
    COAST = "coast"
    PLAINS = "plains"
    FOREST = "forest"
    HILLS = "hills"
    MOUNTAINS = "mountains"
    RIVER = "river"


# Movement point cost to enter each terrain type. None = impassable.
TERRAIN_MOVE_COST: dict[TerrainType, int | None] = {
    TerrainType.OCEAN:     None,
    TerrainType.COAST:     1,
    TerrainType.PLAINS:    1,
    TerrainType.FOREST:    2,
    TerrainType.HILLS:     2,
    TerrainType.MOUNTAINS: 3,
    TerrainType.RIVER:     1,
}


class TurnPhase(str, Enum):
    ROLL = "roll"    # waiting for player to roll dice
    MOVE = "move"    # dice rolled, player may move


class Tile(BaseModel):
    x: int
    y: int
    terrain: TerrainType
    elevation: float = Field(ge=0.0, le=1.0)


class Player(BaseModel):
    id: str
    name: str
    position: tuple[int, int]
    gold: int = 100
    movement_remaining: int = 0
    movement_total: int = 0


class GameState(BaseModel):
    game_id: str
    player: Player
    map_width: int
    map_height: int
    tiles: list[Tile]
    turn: int = 1
    phase: TurnPhase = TurnPhase.ROLL
    seed: int


class NewGameRequest(BaseModel):
    player_name: str
    map_width: int = Field(default=40, ge=10, le=100)
    map_height: int = Field(default=30, ge=10, le=80)
    seed: int | None = None


class RollResult(BaseModel):
    roll: int
    movement_total: int
    message: str
    game_state: GameState


class MoveRequest(BaseModel):
    game_id: str
    dx: int = Field(ge=-1, le=1)
    dy: int = Field(ge=-1, le=1)


class MoveToRequest(BaseModel):
    tx: int
    ty: int


class MoveResult(BaseModel):
    new_position: tuple[int, int]
    terrain: TerrainType
    move_cost: int
    movement_remaining: int
    message: str
    game_state: GameState


class MoveToResult(BaseModel):
    new_position: tuple[int, int]
    terrain: TerrainType
    total_cost: int
    movement_remaining: int
    path: list[tuple[int, int]]
    message: str
    game_state: GameState


class EndTurnResult(BaseModel):
    turn: int
    message: str
    game_state: GameState


class SavedGame(BaseModel):
    game_id: str
    player_name: str
    turn: int
    saved_at: str


class GameListResponse(BaseModel):
    saves: list[SavedGame]


class ErrorResponse(BaseModel):
    detail: str


def tile_map(state: GameState) -> dict[tuple[int, int], Tile]:
    return {(t.x, t.y): t for t in state.tiles}
