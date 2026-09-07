#!/usr/bin/env python3
"""Local API + static UI for Cola de Buques Rosario (Up-River)."""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
WEB = ROOT / "web"

app = FastAPI(title="Cola Buques Rosario", version="1.0.0")


def _load(name: str):
    path = DATA / name
    if not path.exists():
        sample = DATA / f"sample-{name}"
        path = sample if sample.exists() else path
    if not path.exists():
        return JSONResponse({"error": f"missing {name}"}, status_code=404)
    return JSONResponse(json.loads(path.read_text(encoding="utf-8")))


@app.get("/api/health")
def health():
    return {"ok": True, "service": "cola-buques-rosario"}


@app.get("/api/vessels")
def vessels():
    return _load("vessels.json")


@app.get("/api/trucks")
def trucks():
    return _load("trucks.json")


@app.get("/api/terminals")
def terminals():
    """Approximate WGS84 coords for Up-River grain terminals (NABSA zone map)."""
    return _load("terminals.json")


@app.get("/")
def index():
    return FileResponse(WEB / "index.html")


app.mount("/static", StaticFiles(directory=str(WEB / "static")), name="static")


if __name__ == "__main__":
    import os
    import uvicorn

    port = int(os.environ.get("PORT", "5173"))
    uvicorn.run("server:app", host="0.0.0.0", port=port, reload=False)
