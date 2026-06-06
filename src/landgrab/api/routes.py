"""FastAPI route definitions."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from landgrab.core import game as game_engine
from landgrab.models.game_state import (
    EndTurnResult,
    GameListResponse,
    GameState,
    MoveRequest,
    MoveResult,
    MoveToRequest,
    MoveToResult,
    NewGameRequest,
    RollResult,
)

router = APIRouter(prefix="/api")


@router.post("/games", response_model=GameState, status_code=201)
def create_game(req: NewGameRequest) -> GameState:
    return game_engine.new_game(
        player_name=req.player_name,
        width=req.map_width,
        height=req.map_height,
        seed=req.seed,
    )


@router.get("/games", response_model=GameListResponse)
def list_games() -> GameListResponse:
    return GameListResponse(saves=game_engine.list_saves())


@router.get("/games/{game_id}", response_model=GameState)
def get_game(game_id: str) -> GameState:
    try:
        return game_engine.load_game(game_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Game {game_id!r} not found")


@router.post("/games/{game_id}/roll", response_model=RollResult)
def roll(game_id: str) -> RollResult:
    try:
        return game_engine.roll_for_turn(game_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Game {game_id!r} not found")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/games/{game_id}/move", response_model=MoveResult)
def move(game_id: str, req: MoveRequest) -> MoveResult:
    try:
        return game_engine.move(game_id, req.dx, req.dy)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Game {game_id!r} not found")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/games/{game_id}/move-to", response_model=MoveToResult)
def move_to(game_id: str, req: MoveToRequest) -> MoveToResult:
    try:
        return game_engine.move_to(game_id, req.tx, req.ty)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Game {game_id!r} not found")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/games/{game_id}/end-turn", response_model=EndTurnResult)
def end_turn(game_id: str) -> EndTurnResult:
    try:
        return game_engine.end_turn(game_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Game {game_id!r} not found")
