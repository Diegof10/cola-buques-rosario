#!/usr/bin/env python3
"""API + static UI for Cola de Buques Rosario (Up-River).

On Render the filesystem is ephemeral/read-only for the app tree, so vessel
refreshes write under /tmp (or an in-memory cache) when data/ is not writable.
"""
from __future__ import annotations

import json
import re
import unicodedata
import os
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parent
BUNDLED_DATA = ROOT / "data"
WEB = ROOT / "web"
SCRIPTS = ROOT / "scripts"

# Prefer writable dir for live refreshes (Render-friendly).
_ENV_DATA = os.environ.get("DATA_DIR", "").strip()
WRITABLE_DATA = Path(_ENV_DATA) if _ENV_DATA else Path("/tmp/cola-buques-data")

# Stale after this many seconds (~45 min default).
REFRESH_MAX_AGE_SEC = int(os.environ.get("VESSELS_MAX_AGE_SEC", str(45 * 60)))
REFRESH_TIMEOUT_SEC = int(os.environ.get("VESSELS_REFRESH_TIMEOUT_SEC", "50"))

sys.path.insert(0, str(SCRIPTS))

app = FastAPI(title="Cola Buques Rosario", version="1.2.0")

_cache_lock = threading.Lock()
_refresh_lock = threading.Lock()
_vessels_cache: dict[str, Any] | None = None
_vessels_cached_at: float | None = None  # monotonic
_vessels_source_path: str | None = None
_refresh_in_progress = False
_last_refresh_error: str | None = None
_last_refresh_at: str | None = None


def _parse_updated_at(payload: dict[str, Any] | None) -> float | None:
    if not payload:
        return None
    raw = payload.get("updated_at")
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except ValueError:
        return None


def _age_seconds(payload: dict[str, Any] | None, file_mtime: float | None = None) -> float | None:
    ts = _parse_updated_at(payload)
    if ts is not None:
        return max(0.0, time.time() - ts)
    if file_mtime is not None:
        return max(0.0, time.time() - file_mtime)
    if _vessels_cached_at is not None:
        return max(0.0, time.monotonic() - _vessels_cached_at)
    return None


def _is_stale(payload: dict[str, Any] | None, file_mtime: float | None = None) -> bool:
    age = _age_seconds(payload, file_mtime)
    if age is None:
        return True
    return age >= REFRESH_MAX_AGE_SEC


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return None


def _candidate_vessel_paths() -> list[Path]:
    return [
        WRITABLE_DATA / "vessels.json",
        BUNDLED_DATA / "vessels.json",
        BUNDLED_DATA / "sample-vessels.json",
        WRITABLE_DATA / "sample-vessels.json",
    ]


def _path_rank(path: Path) -> int:
    name = path.name
    if name == "vessels.json":
        return 0
    if name == "sample-vessels.json":
        return 1
    return 2


def _load_vessels_from_disk() -> tuple[dict[str, Any] | None, Path | None]:
    best: dict[str, Any] | None = None
    best_path: Path | None = None
    best_ts = -1.0
    best_rank = 99
    for path in _candidate_vessel_paths():
        payload = _read_json(path)
        if not payload:
            continue
        ts = _parse_updated_at(payload)
        if ts is None:
            try:
                ts = path.stat().st_mtime
            except OSError:
                ts = 0.0
        rank = _path_rank(path)
        if ts > best_ts or (ts == best_ts and rank < best_rank):
            best_ts = ts
            best_rank = rank
            best = payload
            best_path = path
    return best, best_path


def _set_vessels_cache(payload: dict[str, Any], source: str | None = None) -> None:
    global _vessels_cache, _vessels_cached_at, _vessels_source_path
    with _cache_lock:
        _vessels_cache = payload
        _vessels_cached_at = time.monotonic()
        _vessels_source_path = source


def _get_vessels_cache() -> dict[str, Any] | None:
    with _cache_lock:
        return _vessels_cache


def _ensure_writable_data() -> Path:
    WRITABLE_DATA.mkdir(parents=True, exist_ok=True)
    # Seed trucks/terminals from bundled data if missing (read-only app dir).
    for name in ("trucks.json", "sample-trucks.json", "terminals.json", "sample-vessels.json"):
        dest = WRITABLE_DATA / name
        src = BUNDLED_DATA / name
        if not dest.exists() and src.exists():
            try:
                dest.write_bytes(src.read_bytes())
            except OSError:
                pass
    return WRITABLE_DATA


def _run_refresh(*, refresh_trucks: bool = True) -> dict[str, Any]:
    global _last_refresh_error, _last_refresh_at, _refresh_in_progress
    from refresh_data import ensure_trucks, refresh_vessels  # type: ignore

    data_dir = _ensure_writable_data()
    try:
        payload = refresh_vessels(
            data_dir,
            write_sample=False,
            download_sailed=False,
            timeout=min(REFRESH_TIMEOUT_SEC, 55),
        )
        payload = dict(payload)
        payload["refreshed_via"] = "server"
        if refresh_trucks:
            try:
                trucks = ensure_trucks(
                    data_dir,
                    write_sample=False,
                    timeout=min(REFRESH_TIMEOUT_SEC, 45),
                )
                payload["trucks_refreshed"] = {
                    "source": trucks.get("source"),
                    "date": trucks.get("date"),
                    "total_camiones": trucks.get("total_camiones"),
                }
            except Exception as tex:
                print(f"[refresh] trucks failed: {tex}", file=sys.stderr)
                payload["trucks_refreshed"] = {"error": str(tex)}
        _set_vessels_cache(payload, str(data_dir / "vessels.json"))
        _last_refresh_error = None
        _last_refresh_at = payload.get("updated_at")
        return payload
    except Exception as ex:
        _last_refresh_error = str(ex)
        raise
    finally:
        with _refresh_lock:
            _refresh_in_progress = False


def _trigger_background_refresh() -> bool:
    """Start a background refresh if none is running. Returns True if started."""
    global _refresh_in_progress
    with _refresh_lock:
        if _refresh_in_progress:
            return False
        _refresh_in_progress = True

    def worker() -> None:
        try:
            _run_refresh()
        except Exception as ex:
            print(f"[refresh] background failed: {ex}", file=sys.stderr)

    threading.Thread(target=worker, daemon=True, name="nabsa-refresh").start()
    return True


def get_vessels_payload(*, force_refresh: bool = False) -> dict[str, Any]:
    """Return vessels JSON, refreshing in background when stale."""
    cached = _get_vessels_cache()
    disk, disk_path = _load_vessels_from_disk()

    # Prefer freshest between memory and disk.
    chosen = cached
    chosen_path = _vessels_source_path
    if disk is not None:
        cached_ts = _parse_updated_at(cached) or 0.0
        disk_ts = _parse_updated_at(disk) or 0.0
        if disk_ts >= cached_ts or chosen is None:
            chosen = disk
            chosen_path = str(disk_path) if disk_path else None
            if cached is None or disk_ts > cached_ts:
                _set_vessels_cache(disk, chosen_path)

    mtime = None
    if disk_path and disk_path.exists():
        try:
            mtime = disk_path.stat().st_mtime
        except OSError:
            mtime = None

    stale = force_refresh or chosen is None or _is_stale(chosen, mtime)

    if chosen is None:
        # Blocking first load: try refresh, else hard fail.
        try:
            with _refresh_lock:
                global _refresh_in_progress
                if not _refresh_in_progress:
                    _refresh_in_progress = True
                    blocking = True
                else:
                    blocking = False
            if blocking:
                return _run_refresh()
            # Another thread refreshing — wait briefly.
            for _ in range(40):
                time.sleep(0.25)
                c = _get_vessels_cache()
                if c is not None:
                    return c
            raise RuntimeError("vessels unavailable")
        except Exception as ex:
            return {
                "error": "vessels unavailable",
                "detail": str(ex),
                "updated_at": None,
                "vessels": [],
                "live": False,
                "parse_ok": False,
            }

    if stale:
        _trigger_background_refresh()

    out = dict(chosen)
    age = _age_seconds(chosen, mtime)
    out["cache"] = {
        "stale": bool(stale),
        "age_seconds": int(age) if age is not None else None,
        "max_age_seconds": REFRESH_MAX_AGE_SEC,
        "refresh_in_progress": _refresh_in_progress,
        "source_path": chosen_path,
        "last_refresh_error": _last_refresh_error,
        "last_refresh_at": _last_refresh_at,
    }
    return out


def _load_static(name: str) -> JSONResponse:
    """Load trucks/terminals from writable then bundled data.

    Prefer freshest trucks.json (by updated_at) over sample-* so a live MAGyP
    scrape is never shadowed by an older sample seed.
    """
    if name == "trucks.json":
        payload = _load_trucks_payload()
        if payload:
            return JSONResponse(payload)
        return JSONResponse({"error": "missing trucks.json"}, status_code=404)

    for base in (WRITABLE_DATA, BUNDLED_DATA):
        path = base / name
        if path.exists():
            try:
                return JSONResponse(json.loads(path.read_text(encoding="utf-8")))
            except Exception:
                continue
        sample = base / f"sample-{name}"
        if sample.exists():
            try:
                return JSONResponse(json.loads(sample.read_text(encoding="utf-8")))
            except Exception:
                continue
    return JSONResponse({"error": f"missing {name}"}, status_code=404)




# --- Truck coverage KPI (tn camiones vs demanda Up-River) ---
# Historical calibration (MAGyP / BCR / NABSA / AgroEntregas):
# - MAGyP 2025 Rosario y aledaños 964.503 cam/año ≈ 2.640/día promedio
# - MAGyP daily early Aug 2026 Rosario often ~2.4k–4.5k/day
# - Picos cosecha AgroEntregas/BCR: 5.500–7.000 cam/día
# - Stock Up-River típico ~3,5–5 Mt (BCR/NABSA/AAACI)
# At ~4,8 Mt: promedio anual ~60d (rojo), flujo bueno ~40d (amarillo), picos ≤30d (verde)
GRAIN_COMMODITIES = frozenset({"soja", "maiz", "trigo", "girasol", "sorgo", "cebada"})
TN_PER_TRUCK_DEFAULT = 30
TN_PER_TRUCK_GIRASOL = 25
# Semáforo on days_to_cover (truck flow vs stock): Verde≤30 Alto, Amarillo 30–55 Normal, Rojo>55 Bajo
DAYS_GREEN_MAX = 30
DAYS_YELLOW_MAX = 55


def _norm_dest(s: str) -> str:
    s = unicodedata.normalize("NFD", str(s or "").lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def _is_argentina_dest(raw: str) -> bool:
    n = _norm_dest(raw)
    return n in {"argentina", "ar", "arg"} or n.startswith("argentina ")


def _is_unknown_dest(raw: str) -> bool:
    n = _norm_dest(raw)
    if not n:
        return True
    return n in {
        "not available",
        "n a",
        "na",
        "n/a",
        "unknown",
        "tbd",
        "-",
        "sin destino",
        "otros",
    }


def _effective_destination(v: dict[str, Any]) -> str:
    if v.get("destination_source") == "inferred" and v.get("destination_inferred"):
        return str(v["destination_inferred"]).strip()
    raw = str(v.get("destination") or v.get("destino") or "").strip()
    if not _is_unknown_dest(raw):
        return raw
    if v.get("destination_inferred"):
        return str(v["destination_inferred"]).strip()
    return ""


def _truck_factor(product: str) -> int:
    # Diego: 30 tn/camión general; 25 tn/camión solo girasol. Ignore stale tn fields.
    return TN_PER_TRUCK_GIRASOL if str(product or "").lower() == "girasol" else TN_PER_TRUCK_DEFAULT


def _load_trucks_payload() -> dict[str, Any] | None:
    """Prefer freshest trucks.json (writable then bundled); avoid stale sample when live exists."""
    best: dict[str, Any] | None = None
    best_ts = -1.0
    best_rank = 99
    candidates = [
        (WRITABLE_DATA / "trucks.json", 0),
        (BUNDLED_DATA / "trucks.json", 1),
        (WRITABLE_DATA / "sample-trucks.json", 2),
        (BUNDLED_DATA / "sample-trucks.json", 3),
    ]
    for path, rank in candidates:
        payload = _read_json(path)
        if not payload:
            continue
        ts = _parse_updated_at(payload)
        if ts is None:
            try:
                ts = path.stat().st_mtime
            except OSError:
                ts = 0.0
        # Prefer magyp over sample when timestamps are close/equal.
        src_bonus = 0.5 if payload.get("source") == "magyp" else 0.0
        score = float(ts) + src_bonus
        if score > best_ts or (score == best_ts and rank < best_rank):
            best_ts = score
            best_rank = rank
            best = payload
    return best


def estimate_truck_tn(trucks: dict[str, Any] | None) -> dict[str, Any]:
    by_product = []
    total_camiones = 0
    truck_tn = 0.0
    if trucks:
        for row in trucks.get("by_product") or []:
            product = str(row.get("product") or "").lower()
            camiones = int(row.get("camiones") or 0)
            factor = _truck_factor(product)
            tn = camiones * factor
            by_product.append(
                {
                    "product": product,
                    "label": row.get("label") or product,
                    "camiones": camiones,
                    "tn_per_truck": factor,
                    "tn": tn,
                }
            )
            total_camiones += camiones
            truck_tn += tn
        if not by_product and trucks.get("total_camiones"):
            # Fallback: unknown mix → 30 tn
            total_camiones = int(trucks.get("total_camiones") or 0)
            truck_tn = total_camiones * TN_PER_TRUCK_DEFAULT
    return {
        "truck_tn": truck_tn,
        "total_camiones": total_camiones,
        "by_product": by_product,
        "source": (trucks or {}).get("source"),
        "date": (trucks or {}).get("date"),
        "updated_at": (trucks or {}).get("updated_at"),
    }


def estimate_demand_tn(vessels_payload: dict[str, Any] | None) -> dict[str, Any]:
    vessels = (vessels_payload or {}).get("vessels") or []
    demand_tn = 0.0
    counted = 0
    excluded_ar_tn = 0.0
    excluded_ar_n = 0
    skipped_commodity_n = 0
    for v in vessels:
        if not v.get("up_river"):
            continue
        commodity = str(v.get("commodity") or "").lower()
        if commodity not in GRAIN_COMMODITIES:
            skipped_commodity_n += 1
            continue
        tons = float(v.get("tons") or 0)
        raw = str(v.get("destination") or v.get("destino") or "").strip()
        eff = _effective_destination(v)
        if _is_argentina_dest(raw) or _is_argentina_dest(eff):
            excluded_ar_tn += tons
            excluded_ar_n += 1
            continue
        demand_tn += tons
        counted += 1
    return {
        "demand_tn": demand_tn,
        "vessel_count": counted,
        "excluded_ar_tn": excluded_ar_tn,
        "excluded_ar_count": excluded_ar_n,
        "skipped_non_grain_up_river": skipped_commodity_n,
        "commodities": sorted(GRAIN_COMMODITIES),
    }


def classify_semaforo(days_to_cover: float | None) -> dict[str, Any]:
    """Semáforo by days_to_cover. Label = truck flow vs stock (Alto/Normal/Bajo)."""
    if days_to_cover is None:
        return {
            "color": "gray",
            "code": "sin_datos",
            "label": "Sin datos",
            "hint": "Sin flujo o sin demanda",
        }
    if days_to_cover <= DAYS_GREEN_MAX:
        return {
            "color": "green",
            "code": "verde",
            "label": "Alto",
            "hint": "Flujo alto · ≤ 30 días de cobertura",
        }
    if days_to_cover <= DAYS_YELLOW_MAX:
        return {
            "color": "yellow",
            "code": "amarillo",
            "label": "Normal",
            "hint": "Flujo normal · 30–55 días de cobertura",
        }
    return {
        "color": "red",
        "code": "rojo",
        "label": "Bajo",
        "hint": "Flujo flojo · > 55 días de cobertura",
    }


def compute_coverage(
    vessels_payload: dict[str, Any] | None = None,
    trucks_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if vessels_payload is None:
        vessels_payload = get_vessels_payload(force_refresh=False)
    if trucks_payload is None:
        trucks_payload = _load_trucks_payload()

    trucks_est = estimate_truck_tn(trucks_payload)
    demand_est = estimate_demand_tn(vessels_payload)
    truck_tn = float(trucks_est["truck_tn"] or 0)
    demand_tn = float(demand_est["demand_tn"] or 0)

    coverage_pct = (100.0 * truck_tn / demand_tn) if demand_tn > 0 else None
    days_to_cover = (demand_tn / truck_tn) if truck_tn > 0 else None
    semaforo = classify_semaforo(days_to_cover)

    return {
        "truck_tn": round(truck_tn, 1),
        "demand_tn": round(demand_tn, 1),
        "coverage_pct": round(coverage_pct, 2) if coverage_pct is not None else None,
        "days_to_cover": round(days_to_cover, 1) if days_to_cover is not None else None,
        "semaforo": semaforo,
        "factors": {
            "default_tn_per_truck": TN_PER_TRUCK_DEFAULT,
            "girasol_tn_per_truck": TN_PER_TRUCK_GIRASOL,
        },
        "thresholds_days": {
            "verde_max": DAYS_GREEN_MAX,
            "amarillo_max": DAYS_YELLOW_MAX,
        },
        "trucks": trucks_est,
        "demand": demand_est,
        "vessels_updated_at": (vessels_payload or {}).get("updated_at"),
        "note": (
            "Demanda = tn anunciadas Up-River de soja/maíz/trigo/girasol/sorgo/cebada "
            "excluyendo destino Argentina / Descarga AR. "
            "Tn camiones = Σ camiones×30 (×25 girasol)."
        ),
    }

@app.on_event("startup")
def _startup_refresh() -> None:
    # Warm cache from disk; kick a background NABSA (+ trucks) refresh if stale/missing.
    disk, path = _load_vessels_from_disk()
    if disk is not None:
        _set_vessels_cache(disk, str(path) if path else None)
    mtime = None
    if path and path.exists():
        try:
            mtime = path.stat().st_mtime
        except OSError:
            pass
    trucks = _load_trucks_payload()
    trucks_stale = (
        trucks is None
        or trucks.get("source") != "magyp"
        or _is_stale(trucks)
    )
    if disk is None or _is_stale(disk, mtime) or trucks_stale:
        _trigger_background_refresh()


@app.get("/api/health")
def health():
    cached = _get_vessels_cache()
    if cached is None:
        cached, _ = _load_vessels_from_disk()
    age = _age_seconds(cached)
    return {
        "ok": True,
        "service": "cola-buques-rosario",
        "vessels_updated_at": (cached or {}).get("updated_at"),
        "vessels_age_seconds": int(age) if age is not None else None,
        "vessels_stale": _is_stale(cached),
        "refresh_in_progress": _refresh_in_progress,
        "refresh_max_age_seconds": REFRESH_MAX_AGE_SEC,
        "last_refresh_error": _last_refresh_error,
        "writable_data": str(WRITABLE_DATA),
    }


@app.get("/api/vessels")
def vessels(refresh: int = 0):
    payload = get_vessels_payload(force_refresh=bool(refresh))
    if payload.get("error") and not payload.get("vessels"):
        return JSONResponse(payload, status_code=503)
    return JSONResponse(payload)


@app.post("/api/vessels/refresh")
def vessels_refresh():
    """Force a NABSA refresh (sync, may take ~30–50s)."""
    global _refresh_in_progress
    with _refresh_lock:
        if _refresh_in_progress:
            return JSONResponse(
                {
                    "ok": False,
                    "message": "refresh already in progress",
                    "refresh_in_progress": True,
                },
                status_code=409,
            )
        _refresh_in_progress = True
    try:
        payload = _run_refresh()
        return {
            "ok": True,
            "updated_at": payload.get("updated_at"),
            "counts": payload.get("counts"),
            "live": payload.get("live"),
            "parse_ok": payload.get("parse_ok"),
        }
    except Exception as ex:
        # Fall back to last good cache
        cached = get_vessels_payload(force_refresh=False)
        return JSONResponse(
            {
                "ok": False,
                "error": str(ex),
                "fallback_updated_at": cached.get("updated_at"),
            },
            status_code=502,
        )


@app.get("/api/trucks")
def trucks():
    return _load_static("trucks.json")


@app.post("/api/trucks/refresh")
def trucks_refresh():
    """Force MAGyP trucks scrape into writable data dir."""
    from refresh_data import ensure_trucks  # type: ignore

    data_dir = _ensure_writable_data()
    try:
        payload = ensure_trucks(
            data_dir,
            write_sample=False,
            timeout=min(REFRESH_TIMEOUT_SEC, 45),
        )
        return {
            "ok": payload.get("source") == "magyp",
            "source": payload.get("source"),
            "date": payload.get("date"),
            "total_camiones": payload.get("total_camiones"),
            "national_total": payload.get("national_total"),
            "updated_at": payload.get("updated_at"),
            "source_note": payload.get("source_note"),
        }
    except Exception as ex:
        return JSONResponse({"ok": False, "error": str(ex)}, status_code=502)


@app.get("/api/terminals")
def terminals():
    """Approximate WGS84 coords for Up-River grain terminals (NABSA zone map)."""
    return _load_static("terminals.json")



@app.get("/api/coverage")
def coverage():
    """Truck tons vs Up-River grain export demand + semáforo (días cobertura)."""
    try:
        payload = compute_coverage()
        return JSONResponse(payload)
    except Exception as ex:
        return JSONResponse({"error": "coverage unavailable", "detail": str(ex)}, status_code=500)


@app.get("/")
def index():
    return FileResponse(WEB / "index.html")


app.mount("/static", StaticFiles(directory=str(WEB / "static")), name="static")


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", "5173"))
    uvicorn.run("server:app", host="0.0.0.0", port=port, reload=False)
