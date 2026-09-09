"""Vercel serverless entry — re-exports the FastAPI app."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from server import app  # noqa: E402

# ASGI app for @vercel/python
__all__ = ["app"]
