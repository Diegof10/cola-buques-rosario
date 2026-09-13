"""Put repo root + scripts/ on sys.path so tests import stock_math offline."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
for p in (ROOT, SCRIPTS):
    s = str(p)
    if s not in sys.path:
        sys.path.insert(0, s)
