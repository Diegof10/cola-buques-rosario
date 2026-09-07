#!/usr/bin/env python3
"""Fetch NABSA lineup PDF and write data/vessels.json (+ optional sailed).
Also writes/keeps data/trucks.json (seed if MAGyP/BCR scrape fails).
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

try:
    import requests
    import pdfplumber
except ImportError:
    print("Install deps: .venv/bin/pip install -r requirements.txt", file=sys.stderr)
    raise

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
VESSEL_URL = "https://www.nabsa.com.ar/assets/vessel_update.pdf"
SAILED_URL = "https://www.nabsa.com.ar/assets/vessels_sailed_update.pdf"

UP_RIVER_PORTS = {
    "SAN LORENZO",
    "ROSARIO",
    "VILLA CONSTITUCION",
    "SAN NICOLAS",
    "RAMALLO",
}

COMMODITY_MAP = {
    "SOYBEANMEAL": "soja",
    "SOYA BEAN": "soja",
    "SOYBEAN OIL": "soja",
    "SOYBEANOIL REFINED": "soja",
    "SOYA BEAN OIL (BLEND)": "soja",
    "SOYA HULL PELLETS": "soja",
    "HULL PELLETS": "soja",
    "CORN": "maiz",
    "CORN FLINT": "maiz",
    "WHEAT": "trigo",
    "SORGHUM": "sorgo",
    "SUN FLOWER OIL": "girasol",
    "SUN FLOWER OIL (HIGHOLEIC)": "girasol",
    "SUN FLOWER PELLETS": "girasol",
    "SUN FLOWER MEAL PELLETS": "girasol",
    "BARLEY": "cebada",
    "BIODIESEL": "biodiesel",
}

COMMODITY_LABEL = {
    "soja": "Soja",
    "maiz": "Maíz",
    "trigo": "Trigo",
    "sorgo": "Sorgo",
    "girasol": "Girasol",
    "cebada": "Cebada",
    "biodiesel": "Biodiésel",
    "otro": "Otro",
}


def ar_tz_now() -> datetime:
    return datetime.now(timezone(timedelta(hours=-3)))


def parse_tons(raw: str | None) -> float | None:
    if not raw:
        return None
    s = str(raw).strip().replace(" ", "")
    if not s:
        return None
    # NABSA uses '.' as thousands separator: 33.000 -> 33000
    if re.fullmatch(r"\d{1,3}(\.\d{3})+", s):
        return float(s.replace(".", ""))
    if re.fullmatch(r"\d+\.\d{3}", s):
        return float(s.replace(".", ""))
    try:
        return float(s.replace(",", "."))
    except ValueError:
        digits = re.sub(r"[^\d.]", "", s)
        if not digits:
            return None
        if digits.count(".") == 1 and len(digits.split(".")[-1]) == 3:
            return float(digits.replace(".", ""))
        try:
            return float(digits)
        except ValueError:
            return None


def zone_for(port: str, terminal: str) -> str:
    t = (terminal or "").upper()
    p = (port or "").upper()
    if "TIMBUES" in t or "TIMBÚES" in t or "TIMBUÉ" in t:
        return "Timbúes"
    if "PUNTA ALVEAR" in t:
        return "Punta Alvear"
    if "GRAL. LAGOS" in t or "GENERAL LAGOS" in t:
        return "Gral. Lagos"
    if "ARROYO SECO" in t:
        return "Arroyo Seco"
    if p == "SAN LORENZO":
        return "San Lorenzo"
    if p == "ROSARIO":
        return "Rosario"
    if p == "VILLA CONSTITUCION":
        return "Villa Constitución"
    if p == "SAN NICOLAS":
        return "San Nicolás"
    if p == "RAMALLO":
        return "Ramallo"
    return port.title() if port else "Otro"


def classify_status(eta: str, etb: str, etf: str) -> str:
    e = f"{eta} {etb} {etf}".upper()
    if "ETF" in e or etf.strip().upper().startswith("ETF"):
        return "cargando"  # finishing / at berth wrapping up
    if "ETB" in e or etb.strip().upper().startswith("ETB") or etb.strip().upper() == "ETB":
        return "cargando"
    if "AT REC" in e or "AT CZONE" in e or "AT S.NICO" in e or "ROADS" in e:
        return "en_rada"
    if "ETA" in e:
        return "arribando"
    if etb or etf:
        return "cargando"
    return "en_cola"


def map_commodity(raw: str) -> tuple[str, str]:
    key = COMMODITY_MAP.get((raw or "").strip().upper(), "otro")
    label = COMMODITY_LABEL.get(key, raw.title() if raw else "Otro")
    if key == "otro" and raw:
        label = raw.title()
    return key, label


def download(url: str, dest: Path) -> bool:
    try:
        r = requests.get(url, timeout=60, headers={"User-Agent": "cola-buques-rosario/1.0"})
        r.raise_for_status()
        dest.write_bytes(r.content)
        print(f"OK download {url} -> {dest.name} ({len(r.content)} bytes)")
        return True
    except Exception as ex:
        print(f"FAIL download {url}: {ex}", file=sys.stderr)
        return False


def parse_lineup(pdf_path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    vessels: list[dict[str, Any]] = []
    meta: dict[str, Any] = {"source": "NABSA", "file": pdf_path.name}
    with pdfplumber.open(pdf_path) as pdf:
        # header text
        first = (pdf.pages[0].extract_text() or "").splitlines()
        for line in first[:5]:
            if "Line Up" in line or "Circ" in line:
                meta["header"] = line.strip()
                m = re.search(r"September\s+(\d+),\s+(\d{4})", line)
                if m:
                    meta["lineup_date"] = f"{m.group(2)}-09-{int(m.group(1)):02d}"
                m2 = re.search(r"Circ\.?\s*Nbr\.?:\s*(\d+)", line, re.I)
                if m2:
                    meta["circular"] = m2.group(1)
                break

        for page in pdf.pages:
            for table in page.extract_tables() or []:
                for row in table:
                    if not row or len(row) < 9:
                        continue
                    port = (row[0] or "").strip()
                    if not port or port.upper() == "PORT":
                        continue
                    vessel = (row[2] or "").strip()
                    if not vessel or vessel.upper() == "NIL":
                        continue
                    terminal = (row[1] or "").strip()
                    eta = (row[3] or "").strip()
                    etb = (row[4] or "").strip()
                    etf = (row[5] or "").strip()
                    ops = (row[6] or "").strip()
                    tons_raw = (row[7] or "").strip()
                    commodity_raw = (row[8] or "").strip()
                    dest = (row[9] or "").strip() if len(row) > 9 else ""
                    origin = (row[10] or "").strip() if len(row) > 10 else ""
                    charterer = (row[11] or "").strip() if len(row) > 11 else ""

                    ck, cl = map_commodity(commodity_raw)
                    status = classify_status(eta, etb, etf)
                    tons = parse_tons(tons_raw)
                    zone = zone_for(port, terminal)
                    up_river = port.upper() in UP_RIVER_PORTS

                    vessels.append(
                        {
                            "vessel": vessel,
                            "port": port.title() if port != port.upper() else port.title(),
                            "port_raw": port,
                            "terminal": terminal,
                            "zone": zone,
                            "eta": eta,
                            "etb": etb,
                            "etf": etf,
                            "ops": ops,
                            "tons": tons,
                            "tons_raw": tons_raw,
                            "commodity": ck,
                            "commodity_label": cl,
                            "commodity_raw": commodity_raw,
                            "destination": dest,
                            "origin": origin,
                            "charterer": charterer,
                            "status": status,
                            "up_river": up_river,
                        }
                    )
    return vessels, meta



def _history_7d(today: str) -> list[dict[str, Any]]:
    from datetime import date, timedelta
    d0 = date.fromisoformat(today)
    return [
        {"date": (d0 - timedelta(days=i)).isoformat(), "camiones": 3200 + (i * 37) % 400}
        for i in range(6, -1, -1)
    ]


def seed_trucks() -> dict[str, Any]:
    """Realistic recent daily truck inflows (camiones) by zone/product for Gran Rosario."""
    today = ar_tz_now().strftime("%Y-%m-%d")
    # Approximate harvest-season style volumes (units = trucks)
    by_product = [
        {"product": "soja", "label": "Soja", "camiones": 1840, "tn": 55200},
        {"product": "maiz", "label": "Maíz", "camiones": 1260, "tn": 37800},
        {"product": "trigo", "label": "Trigo", "camiones": 420, "tn": 12600},
        {"product": "sorgo", "label": "Sorgo", "camiones": 95, "tn": 2850},
        {"product": "girasol", "label": "Girasol", "camiones": 110, "tn": 3300},
    ]
    by_zone = [
        {
            "zone": "San Lorenzo / Timbúes",
            "camiones": 1680,
            "by_product": {"soja": 820, "maiz": 540, "trigo": 180, "sorgo": 40, "girasol": 50},
        },
        {
            "zone": "Rosario",
            "camiones": 720,
            "by_product": {"soja": 380, "maiz": 220, "trigo": 90, "sorgo": 15, "girasol": 15},
        },
        {
            "zone": "Punta Alvear / Gral. Lagos",
            "camiones": 780,
            "by_product": {"soja": 400, "maiz": 280, "trigo": 70, "sorgo": 20, "girasol": 25},
        },
        {
            "zone": "Arroyo Seco",
            "camiones": 545,
            "by_product": {"soja": 240, "maiz": 220, "trigo": 80, "sorgo": 20, "girasol": 20},
        },
    ]
    return {
        "updated_at": ar_tz_now().isoformat(),
        "date": today,
        "source": "sample",
        "source_note": "Muestra realista (seed). Ejecutar refresh intenta MAGyP/BCR; si falla se conserva este JSON.",
        "unit": "camiones",
        "total_camiones": sum(p["camiones"] for p in by_product),
        "total_tn": sum(p["tn"] for p in by_product),
        "by_product": by_product,
        "by_zone": by_zone,
        "history_7d": _history_7d(today),
    }


def try_fetch_trucks() -> dict[str, Any] | None:
    """Best-effort: MAGyP / BCR pages are dynamic; return None to keep seed."""
    candidates = [
        "https://www.magyp.gob.ar/",
        "https://www.bcr.com.ar/",
    ]
    for url in candidates:
        try:
            r = requests.get(url, timeout=20, headers={"User-Agent": "cola-buques-rosario/1.0"})
            if r.status_code == 200:
                print(f"Reachable {url} (no structured truck API — keeping seed trucks)")
        except Exception as ex:
            print(f"Truck source skip {url}: {ex}")
    return None


def main() -> int:
    DATA.mkdir(parents=True, exist_ok=True)
    pdf_path = DATA / "vessel_update.pdf"
    live = download(VESSEL_URL, pdf_path)
    sailed_ok = download(SAILED_URL, DATA / "vessels_sailed_update.pdf")

    vessels: list[dict[str, Any]] = []
    meta: dict[str, Any] = {}
    parse_ok = False
    if pdf_path.exists():
        try:
            vessels, meta = parse_lineup(pdf_path)
            parse_ok = True
            print(f"Parsed {len(vessels)} vessel rows from NABSA")
        except Exception as ex:
            print(f"Parse failed: {ex}", file=sys.stderr)

    if not parse_ok:
        sample = DATA / "sample-vessels.json"
        if sample.exists():
            print("Using sample-vessels.json fallback")
            payload = json.loads(sample.read_text(encoding="utf-8"))
            DATA.joinpath("vessels.json").write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        else:
            print("No vessels data available", file=sys.stderr)
            return 1
    else:
        up = [v for v in vessels if v.get("up_river")]
        payload = {
            "updated_at": ar_tz_now().isoformat(),
            "live": live,
            "parse_ok": True,
            "source": "NABSA vessel_update.pdf",
            "source_url": VESSEL_URL,
            "meta": meta,
            "sailed_pdf": sailed_ok,
            "counts": {
                "all": len(vessels),
                "up_river": len(up),
                "arribando": sum(1 for v in up if v["status"] == "arribando"),
                "en_cola": sum(1 for v in up if v["status"] in ("en_cola", "en_rada", "cargando")),
                "cargando": sum(1 for v in up if v["status"] == "cargando"),
                "en_rada": sum(1 for v in up if v["status"] == "en_rada"),
            },
            "vessels": vessels,
        }
        DATA.joinpath("vessels.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        # also refresh sample snapshot for offline demo
        DATA.joinpath("sample-vessels.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"Wrote data/vessels.json (up_river={len(up)})")

    trucks_path = DATA / "trucks.json"
    live_trucks = try_fetch_trucks()
    if live_trucks:
        trucks_path.write_text(json.dumps(live_trucks, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        if not trucks_path.exists():
            seed = seed_trucks()
            trucks_path.write_text(json.dumps(seed, ensure_ascii=False, indent=2), encoding="utf-8")
            DATA.joinpath("sample-trucks.json").write_text(
                json.dumps(seed, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            print("Wrote seed data/trucks.json")
        else:
            # keep existing; ensure sample copy
            if not (DATA / "sample-trucks.json").exists():
                (DATA / "sample-trucks.json").write_text(trucks_path.read_text(encoding="utf-8"), encoding="utf-8")
            print("Kept existing data/trucks.json (seed)")

    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
