"""Application entry point."""

from __future__ import annotations

from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from landgrab.api.routes import router

app = FastAPI(title="LandGrab", version="0.1.0")
app.include_router(router)

# Serve the frontend from /frontend
_frontend = Path(__file__).parent.parent.parent / "frontend"
if _frontend.exists():
    app.mount("/", StaticFiles(directory=str(_frontend), html=True), name="frontend")


def run() -> None:
    uvicorn.run("landgrab.main:app", host="0.0.0.0", port=8000, reload=True)


if __name__ == "__main__":
    run()
