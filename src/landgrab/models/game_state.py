"""Pydantic models for game state serialization."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class TerrainType(StrEnum):
    # Water
    OCEAN       = "ocean"
    # Coastal
    COASTAL     = "coastal"
    FLOODPLAIN  = "floodplain"
    CLIFF_COAST = "cliff_coast"
    # Base terrains
    PLAIN       = "plain"
    GRASSLAND   = "grassland"
    FOREST      = "forest"
    THICK_FOREST = "thick_forest"
    JUNGLE      = "jungle"
    MARSH       = "marsh"
    DESERT      = "desert"
    DEEP_DESERT = "deep_desert"
    TUNDRA      = "tundra"
    FROZEN_TUNDRA = "frozen_tundra"
    # Overlay
    RIVER       = "river"


class ModifierType(StrEnum):
    FLAT     = "flat"
    HILLS    = "hills"
    MOUNTAIN = "mountain"


class TurnPhase(StrEnum):
    ROLL = "roll"
    MOVE = "move"


class Tile(BaseModel):
    x: int
    y: int
    terrain: TerrainType
    modifier: ModifierType = ModifierType.FLAT
    elevation: float = Field(ge=0.0, le=1.0)
    hills_scalar: float = Field(default=0.0, ge=0.0, le=1.0)
    move_cost: float | None = None  # None = impassable
    is_river: bool = False


class WorldSettings(BaseModel):
    climate:       str = "temperate"
    precipitation: str = "normal"
    age:           str = "old"
    fragmentation: str = "default"


class Player(BaseModel):
    id: str
    name: str
    position: tuple[int, int]
    gold: int = 100
    movement_remaining: float = 0
    movement_total: float = 0


class GameState(BaseModel):
    game_id: str
    player: Player
    map_width: int
    map_height: int
    tiles: list[Tile]
    turn: int = 1
    phase: TurnPhase = TurnPhase.ROLL
    seed: int
    world: WorldSettings = Field(default_factory=WorldSettings)


class NewGameRequest(BaseModel):
    player_name: str
    map_width: int = Field(default=60, ge=10, le=200)
    map_height: int = Field(default=40, ge=10, le=150)
    seed: int | None = None
    world: WorldSettings = Field(default_factory=WorldSettings)


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
    modifier: ModifierType
    move_cost: float
    movement_remaining: float
    message: str
    game_state: GameState


class MoveToResult(BaseModel):
    new_position: tuple[int, int]
    terrain: TerrainType
    modifier: ModifierType
    total_cost: float
    movement_remaining: float
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
