# LandGrab — Dev Guide

## Project
Medieval economic strategy game. FastAPI backend + plain JS frontend.  
Python 3.11+, src layout (`src/landgrab/`).

## Setup
```bash
pip install -e ".[dev]"
# or, if noise isn't available (map falls back to pseudo-random):
pip install -e ".[dev]" --no-deps && pip install fastapi uvicorn pydantic numpy pytest httpx ruff mypy pytest-asyncio
```

## Run
```bash
landgrab          # runs uvicorn on http://localhost:8000
# or
python -m landgrab.main
```
Open `http://localhost:8000` in your browser.

## Test
```bash
pytest
```

## Lint / type check
```bash
ruff check src tests
mypy src
```

## Structure
```
src/landgrab/
  main.py          # FastAPI app + static mount
  api/routes.py    # REST endpoints
  core/
    map_gen.py     # Perlin-noise procedural map
    game.py        # new/load/save/move logic
    dice.py        # dice rolling
  models/
    game_state.py  # Pydantic models
frontend/
  index.html
  css/style.css
  js/app.js
saves/             # JSON save files (git-ignored)
tests/
```

## Key design decisions
- Save files are plain JSON in `saves/` — no database needed at this stage.
- Map uses `noise` lib (Perlin) if installed, falls back to seeded random.
- Frontend is vanilla JS with a `<canvas>` map; React migration later if needed.

## Next steps
- [ ] Fog of war
- [ ] Named settlements on the map
- [ ] Economy / resource tiles
- [ ] AI lords
```
