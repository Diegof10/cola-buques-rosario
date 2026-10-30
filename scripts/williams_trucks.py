"""Williams Agroservicios daily trucks .xls → trucks.json schema.

Primary source for /api/trucks. MAGyP builds its table from these same files,
so zone totals match MAGyP 1:1. Parsing is label-based (zone headers, TOTAL,
"Total hoy", product column headers) — never fixed row numbers.
"""
from __future__ import annotations

import sys
import unicodedata
from datetime import date, datetime, timedelta
from typing import Any, Callable

WILLIAMS_BASE = "https://www1.williamsagroservicios.com.ar/files/camiones"
WILLIAMS_PAGE = "https://www.williamsagroservicios.com.ar/informacion-util"
WILLIAMS_NOTE = "Fuente: Williams Agroservicios"

PRODUCTS = ("trigo", "maiz", "sorgo", "cebada", "soja", "girasol")
_HEADER_MAP = {
    "trigo": "trigo", "maiz": "maiz", "sorgo": "sorgo", "cebada": "cebada",
    "soja": "soja", "giras": "girasol", "girasol": "girasol",
    "totales": "total", "total": "total",
}
# Zone header label (normalized prefix) → internal key
_ZONES = (
    ("rosario", "rosario"),
    ("darsena", "darsena"),
    ("puertos de necochea", "necochea"),
    ("necochea", "necochea"),
    ("puertos-b.blanca", "bahia_blanca"),
    ("puertos b.blanca", "bahia_blanca"),
    ("bahia blanca", "bahia_blanca"),
    ("b.blanca", "bahia_blanca"),
)


def williams_url(d: date) -> str:
    return f"{WILLIAMS_BASE}/{d.isoformat()}.xls"


def _norm(v: Any) -> str:
    s = unicodedata.normalize("NFKD", str(v or "")).encode("ascii", "ignore").decode()
    return " ".join(s.lower().split())


def _num(v: Any) -> int | None:
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return int(round(v))
    s = str(v or "").strip().replace(".", "").replace(",", "")
    return int(s) if s.isdigit() else None


def _zone_key(label: str) -> str | None:
    n = _norm(label)
    for prefix, key in _ZONES:
        if n.startswith(prefix):
            return key
    return None


def parse_williams_xls(content: bytes) -> dict[str, Any]:
    """Return {date, zones{key:{total, products{}, vagones}}, national{total, products}}."""
    import xlrd

    book = xlrd.open_workbook(file_contents=content)
    sh = book.sheet_by_index(0)
    rows = [sh.row_values(r) for r in range(sh.nrows)]

    zones: dict[str, dict[str, Any]] = {}
    national: dict[str, Any] | None = None
    report_date: date | None = None
    cols: dict[str, int] = {}
    vag_col: int | None = None
    current: str | None = None
    vag_acc: dict[str, int] = {}

    for row in rows:
        labels = [_norm(c) for c in row]
        first = labels[0] if labels else ""
        # Column header row (zone header or comparison header)
        if any(l in ("trigo",) for l in labels) and any(l in ("soja",) for l in labels):
            cols = {}
            for i, l in enumerate(labels):
                if l in _HEADER_MAP and _HEADER_MAP[l] not in cols:
                    cols[_HEADER_MAP[l]] = i
                if l.startswith("vagones"):
                    vag_col = i
            zk = _zone_key(row[0]) if first else None
            current = zk
            continue
        if first == "codigo" or "codigo" in labels:
            for c in row:
                if isinstance(c, float) and 40000 < c < 60000 and report_date is None:
                    report_date = xlrd.xldate_as_datetime(c, book.datemode).date()
        if first == "total" and current and cols:
            z = {
                "total": _num(row[cols["total"]]) or 0,
                "products": {p: (_num(row[cols[p]]) or 0) for p in PRODUCTS if p in cols},
            }
            tv = _num(row[vag_col]) if vag_col is not None and vag_col < len(row) else None
            z["vagones"] = tv if tv is not None else vag_acc.get(current)
            zones[current] = z
            current = None
            continue
        if first == "total hoy" and cols:
            national = {
                "total": _num(row[cols["total"]]) or 0,
                "products": {p: (_num(row[cols[p]]) or 0) for p in PRODUCTS if p in cols},
            }
            for c in row[1:3]:
                if isinstance(c, float) and 40000 < c < 60000:
                    d2 = xlrd.xldate_as_datetime(c, book.datemode).date()
                    report_date = report_date or d2
            continue
        if current and vag_col is not None and vag_col < len(row):
            v = _num(row[vag_col])
            if v is not None:
                vag_acc[current] = vag_acc.get(current, 0) + v

    if "rosario" not in zones:
        raise ValueError("Williams xls: no se encontró TOTAL de Rosario y zona")
    if national is None:
        tot = sum(z["total"] for z in zones.values())
        prods = {p: sum(z["products"].get(p, 0) for z in zones.values()) for p in PRODUCTS}
        national = {"total": tot, "products": prods}
    if report_date is None:
        raise ValueError("Williams xls: sin fecha de informe")
    vag_vals = [z.get("vagones") for z in zones.values() if z.get("vagones") is not None]
    return {
        "date": report_date.isoformat(),
        "zones": zones,
        "national": national,
        "vagones": sum(vag_vals) if vag_vals else None,
    }


Fetcher = Callable[[str, int], "bytes | None"]


def http_fetch(url: str, timeout: int) -> bytes | None:
    """GET url; None on 404/any error."""
    import urllib.request

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "cola-buques-rosario/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except Exception as ex:
        print(f"Williams fetch miss {url}: {ex}", file=sys.stderr)
        return None


def fetch_williams_days(
    today: date,
    *,
    lookback_days: int = 10,
    fetch: Fetcher = http_fetch,
    timeout: int = 20,
) -> dict[str, dict[str, Any]]:
    """Fetch today and previous days (404 tolerated). Returns {iso_date: parsed}."""
    from concurrent.futures import ThreadPoolExecutor

    days = [today - timedelta(days=i) for i in range(lookback_days + 1)]

    def one(d: date) -> tuple[date, dict[str, Any] | None]:
        blob = fetch(williams_url(d), timeout)
        if not blob:
            return d, None
        try:
            parsed = parse_williams_xls(blob)
        except Exception as ex:
            print(f"Williams parse fail {d}: {ex}", file=sys.stderr)
            return d, None
        return d, parsed

    out: dict[str, dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=6) as ex:
        for d, parsed in ex.map(one, days):
            if parsed:
                parsed["source_url"] = williams_url(d)
                out[parsed["date"]] = parsed
    return out


def _labels() -> dict[str, str]:
    return {"trigo": "Trigo", "maiz": "Maíz", "sorgo": "Sorgo", "cebada": "Cebada",
            "soja": "Soja", "girasol": "Girasol"}


def build_trucks_payload(
    williams_days: dict[str, dict[str, Any]],
    magyp_payload: dict[str, Any] | None,
    *,
    now_iso: str,
) -> dict[str, Any]:
    """Merge Williams days (primary) with MAGyP rows (gap fill) into trucks.json schema."""
    if not williams_days:
        raise ValueError("Williams: sin informes disponibles")
    latest_iso = max(williams_days)
    w = williams_days[latest_iso]
    ros = w["zones"]["rosario"]
    labels = _labels()

    # Day series: MAGyP first, Williams overrides (same underlying data).
    series: dict[str, dict[str, Any]] = {}
    mraw = (magyp_payload or {}).get("raw") or {}
    for r in mraw.get("national_days") or []:
        series[r["date"]] = {
            "date": r["date"], "products": dict(r.get("products") or {}),
            "national_total": int(r.get("national_total") or 0),
            "rosario": int(r.get("rosario") or 0), "source": "magyp",
        }
    for iso, d in williams_days.items():
        series[iso] = {
            "date": iso, "products": dict(d["national"]["products"]),
            "national_total": int(d["national"]["total"]),
            "rosario": int(d["zones"]["rosario"]["total"]), "source": "williams",
        }

    d_latest = date.fromisoformat(latest_iso)
    history_7d = []
    for i in range(6, -1, -1):
        iso = (d_latest - timedelta(days=i)).isoformat()
        history_7d.append({"date": iso, "camiones": series.get(iso, {}).get("rosario", 0)})

    month = latest_iso[:7]
    vagones = w.get("vagones")
    vagones_source = "williams"
    if vagones is None and mraw.get("vagones") is not None and (magyp_payload or {}).get("date") == latest_iso:
        vagones, vagones_source = mraw.get("vagones"), "magyp"
    if vagones is None:
        vagones_source = None

    by_product = [
        {"product": p, "label": labels[p], "camiones": int(ros["products"].get(p, 0))}
        for p in PRODUCTS
    ]
    zones = w["zones"]
    return {
        "updated_at": now_iso,
        "date": latest_iso,
        "source": "williams",
        "source_url": w.get("source_url") or williams_url(d_latest),
        "source_note": f"Rosario y aledaños, por producto real del informe. {WILLIAMS_NOTE}.",
        "source_label": WILLIAMS_NOTE,
        "unit": "camiones",
        "total_camiones": int(ros["total"]),
        "total_tn": None,
        "by_product": by_product,
        "by_zone": [
            {"zone": "Rosario y aledaños", "camiones": int(ros["total"]),
             "by_product": {p["product"]: p["camiones"] for p in by_product}},
        ],
        "history_7d": history_7d,
        "national_total": int(w["national"]["total"]),
        "raw": {
            "page_month": month,
            "date_cell": latest_iso,
            "zones": {
                "rosario": zones.get("rosario", {}).get("total", 0),
                "darsena": zones.get("darsena", {}).get("total", 0),
                "necochea": zones.get("necochea", {}).get("total", 0),
                "bahia_blanca": zones.get("bahia_blanca", {}).get("total", 0),
                "zones_total": sum(z.get("total", 0) for z in zones.values()),
            },
            "zones_by_product": {k: z.get("products", {}) for k, z in zones.items()},
            "national_products": dict(w["national"]["products"]),
            "vagones": vagones,
            "vagones_source": vagones_source,
            "days_parsed": len(series),
            "williams_days": sorted(williams_days),
            "national_days": [
                {k: v for k, v in r.items()}
                for iso, r in sorted(series.items()) if iso.startswith(month)
            ],
        },
    }
