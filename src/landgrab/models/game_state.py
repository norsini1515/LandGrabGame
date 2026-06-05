"""Pydantic models for game state serialization."""

from __future__ import annotations

from enum import Enum
from typing import Any
from pydantic import BaseModel, Field


class TerrainType(str, Enum):
    OCEAN = "ocean"
    COAST = "coast"
    PLAINS = "plains"
    FOREST = "forest"
    HILLS = "hills"
    MOUNTAINS = "mountains"
    RIVER = "river"


class Tile(BaseModel):
    x: int
    y: int
    terrain: TerrainType
    elevation: float = Field(ge=0.0, le=1.0)
    # Future: owner, resources, structures


class Player(BaseModel):
    id: str
    name: str
    position: tuple[int, int]
    gold: int = 100


class GameState(BaseModel):
    game_id: str
    player: Player
    map_width: int
    map_height: int
    # Tiles are stored as a flat list, row-major order
    tiles: list[Tile]
    turn: int = 1
    seed: int


class NewGameRequest(BaseModel):
    player_name: str
    map_width: int = Field(default=40, ge=10, le=100)
    map_height: int = Field(default=30, ge=10, le=80)
    seed: int | None = None


class MoveRequest(BaseModel):
    game_id: str
    # dx/dy: -1, 0, or 1
    dx: int = Field(ge=-1, le=1)
    dy: int = Field(ge=-1, le=1)


class MoveResult(BaseModel):
    new_position: tuple[int, int]
    roll: int
    terrain: TerrainType
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


# Utility to build a dict from tiles for fast lookup
def tile_map(state: GameState) -> dict[tuple[int, int], Tile]:
    return {(t.x, t.y): t for t in state.tiles}
