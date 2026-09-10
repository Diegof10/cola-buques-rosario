#!/usr/bin/env python3
"""Fetch NABSA lineup PDF and write data/vessels.json (+ optional sailed).

Also fetches MAGyP daily trucks HTML → data/trucks.json (keeps previous on scrape failure).
When sailed PDF is downloaded, parses sailed rows → data/sailed_month.json
(per-product export tonnes for the current calendar month).
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

# Conservative charterer → likely foreign destination when NABSA dest is missing.
# Only clear, well-known mappings (do not invent for traders with mixed routes).
CHARTERER_DEST_INFER: dict[str, str] = {
    "AL GHURAIR": "UNITED ARAB EMIR",  # UAE flour/feed group
    "COFCO": "CHINA",
    "CJ INTERNATIONAL": "KOREA",
    "CJ CHEILJEDANG": "KOREA",
    "ARASCO": "SAUDI ARABIA",
    "AL QAIRAWAN": "YEMEN",
}

_UNKNOWN_DEST = {
    "",
    "NOT AVAILABLE",
    "N/A",
    "NA",
    "N A",
    "UNKNOWN",
    "TBD",
    "-",
    "SIN DESTINO",
    "OTROS",
}


def _norm_token(s: str | None) -> str:
    return " ".join(str(s or "").upper().replace("/", " ").split())


def is_unknown_destination(dest: str | None) -> bool:
    return _norm_token(dest) in _UNKNOWN_DEST


def is_unknown_charterer(charterer: str | None) -> bool:
    n = _norm_token(charterer)
    return (not n) or n in _UNKNOWN_DEST


def infer_destination_from_charterer(charterer: str | None) -> str | None:
    """Return NABSA-style country key when charterer maps confidently; else None."""
    if is_unknown_charterer(charterer):
        return None
    n = _norm_token(charterer)
    # Exact key first, then substring (longer keys first).
    if n in CHARTERER_DEST_INFER:
        return CHARTERER_DEST_INFER[n]
    for key, dest in sorted(CHARTERER_DEST_INFER.items(), key=lambda kv: -len(kv[0])):
        if key in n:
            return dest
    return None


def enrich_vessel_destination(v: dict[str, Any]) -> dict[str, Any]:
    """Attach destination_source / destination_inferred; never overwrite NABSA dest."""
    raw = (v.get("destination") or "").strip()
    if not is_unknown_destination(raw):
        v["destination_source"] = "nabsa"
        v["destination_inferred"] = None
        return v
    inferred = infer_destination_from_charterer(v.get("charterer"))
    if inferred:
        v["destination_inferred"] = inferred
        v["destination_source"] = "inferred"
    else:
        v["destination_inferred"] = None
        v["destination_source"] = "nabsa"  # true unknown from NABSA
    return v


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



def parse_sailed_tons(raw: str | None) -> float | None:
    """Parse NABSA sailed Tons with weird spacing / European decimals.

    Examples: ``1 6.999,86`` → 16999.86, ``4 .632,00`` → 4632.0, ``3 7,00`` → 37.0.
    """
    if not raw:
        return None
    s = str(raw).strip().replace(" ", "").replace("\xa0", "")
    if not s:
        return None
    # European thousands '.' / decimal ','
    if "," in s:
        intpart, frac = s.rsplit(",", 1)
        intpart = intpart.replace(".", "")
        try:
            return float(f"{intpart}.{frac}")
        except ValueError:
            return None
    # Dot as thousands: 33.000 / 1.234.567
    if re.fullmatch(r"\d{1,3}(\.\d{3})+", s):
        return float(s.replace(".", ""))
    if re.fullmatch(r"\d+\.\d{3}", s):
        return float(s.replace(".", ""))
    try:
        return float(s)
    except ValueError:
        digits = re.sub(r"[^\d.]", "", s)
        if not digits:
            return None
        try:
            return float(digits)
        except ValueError:
            return None


def map_sailed_commodity(cargo_raw: str | None) -> str:
    """Map NABSA Cargo text → maiz|soja|trigo|girasol|sorgo|cebada|otro (contains)."""
    c = str(cargo_raw or "").lower()
    if "corn" in c:
        return "maiz"
    # Soy complex (meal/oil/beans/hulls) counts against soja stock
    if (
        "soybean meal" in c
        or "soybeanmeal" in c
        or "soybean oil" in c
        or "soybeanoil" in c
        or "soy bean" in c
        or "soybean" in c
        or "soya" in c
    ):
        return "soja"
    if "wheat" in c:
        return "trigo"
    if "sun flower" in c or "sunflower" in c:
        return "girasol"
    if "sorghum" in c:
        return "sorgo"
    if "barley" in c:
        return "cebada"
    return "otro"


def _parse_sailed_date(raw: str | None) -> str | None:
    """DD/MM/YYYY → YYYY-MM-DD."""
    s = str(raw or "").strip()
    m = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{4})", s)
    if not m:
        return None
    d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
    try:
        return f"{y:04d}-{mo:02d}-{d:02d}"
    except Exception:
        return None


def parse_sailed_pdf(pdf_path: Path) -> list[dict[str, Any]]:
    """Extract sailed vessel lines from NABSA vessels_sailed_update.pdf."""
    rows: list[dict[str, Any]] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            for table in page.extract_tables() or []:
                for row in table or []:
                    if not row or len(row) < 7:
                        continue
                    status = str(row[3] or "").strip().upper()
                    if status != "SAILED":
                        continue
                    date_iso = _parse_sailed_date(row[4])
                    if not date_iso:
                        continue
                    tons = parse_sailed_tons(row[5])
                    if tons is None:
                        continue
                    cargo_raw = str(row[6] or "").strip()
                    commodity = map_sailed_commodity(cargo_raw)
                    rows.append(
                        {
                            "date": date_iso,
                            "tons": round(float(tons), 2),
                            "cargo_raw": cargo_raw,
                            "commodity": commodity,
                            "port": str(row[0] or "").strip(),
                            "vessel": str(row[2] or "").strip(),
                        }
                    )
    return rows


def build_sailed_month(
    sailed_rows: list[dict[str, Any]],
    *,
    month: str | None = None,
) -> dict[str, Any]:
    """Aggregate sailed tonnes by product for a calendar month (YYYY-MM)."""
    if not month:
        month = ar_tz_now().strftime("%Y-%m")
    products = {k: 0.0 for k in STOCK_LEDGER_PRODUCTS}
    by_day: dict[str, dict[str, float]] = {}
    raw_count = 0
    ignored_otro = 0.0
    for row in sailed_rows:
        d = str(row.get("date") or "")
        if not d.startswith(month):
            continue
        raw_count += 1
        commodity = str(row.get("commodity") or "otro")
        tons = float(row.get("tons") or 0)
        if commodity not in products:
            ignored_otro += tons
            continue
        products[commodity] += tons
        day = by_day.setdefault(d, {k: 0.0 for k in STOCK_LEDGER_PRODUCTS})
        day[commodity] += tons
    # Round for JSON stability
    products_out = {k: round(v, 2) for k, v in products.items()}
    by_day_out = {
        d: {k: round(v, 2) for k, v in day.items()}
        for d, day in sorted(by_day.items())
    }
    return {
        "month": month,
        "updated_at": ar_tz_now().isoformat(),
        "source": "NABSA vessels_sailed_update.pdf",
        "source_url": SAILED_URL,
        "products": products_out,
        "by_day": by_day_out,
        "rows_in_month": raw_count,
        "ignored_otro_tn": round(ignored_otro, 2),
        "unit": "t",
        "note": (
            "Suma de toneladas SAILED NABSA (todas las filas del PDF) por commodity "
            "en el mes calendario. Complejo soja (meal/oil/bean) → soja; "
            "sun flower → girasol. Productos 'otro' no restan del stock de granos."
        ),
    }


def write_sailed_month(
    data_dir: Path,
    pdf_path: Path | None = None,
    *,
    month: str | None = None,
) -> dict[str, Any] | None:
    """Parse sailed PDF (if present) and write data/sailed_month.json."""
    data_dir = Path(data_dir)
    pdf_path = Path(pdf_path) if pdf_path else data_dir / "vessels_sailed_update.pdf"
    if not pdf_path.exists():
        print(f"WARN sailed: missing {pdf_path.name}", file=sys.stderr)
        return None
    try:
        rows = parse_sailed_pdf(pdf_path)
    except Exception as ex:
        print(f"FAIL parse sailed PDF: {ex}", file=sys.stderr)
        return None
    if not month:
        # Prefer latest date in PDF if same month as AR today; else AR today month
        month = ar_tz_now().strftime("%Y-%m")
        if rows:
            latest = max(str(r.get("date") or "") for r in rows)
            if latest[:7]:
                month = latest[:7]
    payload = build_sailed_month(rows, month=month)
    out = data_dir / "sailed_month.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    prods = payload.get("products") or {}
    print(
        f"Wrote {out} month={payload['month']} rows={payload['rows_in_month']} "
        f"maiz={prods.get('maiz')} soja={prods.get('soja')} trigo={prods.get('trigo')}"
    )
    return payload



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

                    row_v = {
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
                    vessels.append(enrich_vessel_destination(row_v))
    return vessels, meta



MAGYP_TRUCKS_URL = (
    "https://www.magyp.gob.ar/sitio/areas/ss_mercados_agropecuarios/logistica/"
    "_archivos/000023_Posici%C3%B3n%20de%20Camiones%20y%20Vagones/"
    "000020_Entrada%20diaria%20de%20camiones%20y%20vagones%20a%20puertos,"
    "%20f%C3%A1bricas%20y%20molinos%20(por%20zona%20portuaria%20y%20por%20producto).php"
)

MAGYP_PRODUCTS = (
    ("trigo", "Trigo"),
    ("maiz", "Maíz"),
    ("sorgo", "Sorgo"),
    ("cebada", "Cebada"),
    ("soja", "Soja"),
    ("girasol", "Girasol"),
)

_ES_MONTHS = {
    "enero": 1,
    "ene": 1,
    "febrero": 2,
    "feb": 2,
    "marzo": 3,
    "mar": 3,
    "abril": 4,
    "abr": 4,
    "mayo": 5,
    "may": 5,
    "junio": 6,
    "jun": 6,
    "julio": 7,
    "jul": 7,
    "agosto": 8,
    "ago": 8,
    "septiembre": 9,
    "sept": 9,
    "sep": 9,
    "octubre": 10,
    "oct": 10,
    "noviembre": 11,
    "nov": 11,
    "diciembre": 12,
    "dic": 12,
}


def _parse_magyp_int(raw: str | None) -> int:
    """Parse MAGyP ints with dot thousands: '3.223' → 3223."""
    s = str(raw or "").strip().replace("\xa0", "").replace(" ", "")
    if not s or s in {"-", "—"}:
        return 0
    s = s.replace(".", "")
    try:
        return int(s)
    except ValueError:
        digits = re.sub(r"[^\d]", "", s)
        return int(digits) if digits else 0


def _parse_month_year_header(text: str) -> tuple[int, int] | None:
    m = re.search(
        r"(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre)\s+(\d{4})",
        text or "",
        re.I,
    )
    if not m:
        return None
    month = _ES_MONTHS.get(m.group(1).lower())
    if not month:
        return None
    return int(m.group(2)), month


def _parse_day_cell(cell: str, page_year: int, page_month: int) -> str | None:
    """'1-sept' + Septiembre 2026 → '2026-09-01'."""
    m = re.fullmatch(
        r"(\d{1,2})\s*[-/]\s*([a-záéíóúñ]+)",
        (cell or "").strip().lower(),
        re.I,
    )
    if not m:
        return None
    day = int(m.group(1))
    abbr = (
        m.group(2)
        .replace("á", "a")
        .replace("é", "e")
        .replace("í", "i")
        .replace("ó", "o")
        .replace("ú", "u")
    )
    month = _ES_MONTHS.get(abbr) or page_month
    year = page_year
    # Month wrap near year boundary (e.g. page Enero, cell 31-dic)
    if page_month == 1 and month == 12:
        year = page_year - 1
    elif page_month == 12 and month == 1:
        year = page_year + 1
    try:
        from datetime import date as _date

        return _date(year, month, day).isoformat()
    except ValueError:
        return None


class _MagypTableParser:
    """Minimal HTML table extractor (stdlib html.parser)."""

    def __init__(self) -> None:
        from html.parser import HTMLParser

        outer = self

        class _P(HTMLParser):
            def __init__(self) -> None:
                super().__init__()
                self.rows: list[list[str]] = []
                self._cur: list[str] = []
                self._cell: list[str] = []
                self._in_cell = False

            def handle_starttag(self, tag, attrs):  # type: ignore[no-untyped-def]
                if tag in ("td", "th"):
                    self._in_cell = True
                    self._cell = []
                elif tag == "br" and self._in_cell:
                    self._cell.append(" ")

            def handle_endtag(self, tag):  # type: ignore[no-untyped-def]
                if tag in ("td", "th") and self._in_cell:
                    text = re.sub(r"\s+", " ", "".join(self._cell)).strip()
                    self._cur.append(text)
                    self._in_cell = False
                elif tag == "tr":
                    if self._cur:
                        self.rows.append(self._cur)
                    self._cur = []

            def handle_data(self, data):  # type: ignore[no-untyped-def]
                if self._in_cell:
                    self._cell.append(data)

        self._parser = _P()

    def feed(self, html: str) -> list[list[str]]:
        self._parser.feed(html)
        self._parser.close()
        return self._parser.rows


def _scale_products_to_rosario(
    national_products: dict[str, int], rosario: int, national_total: int
) -> list[dict[str, Any]]:
    """Prorrateo nacional → Rosario; suma exacta = rosario (ajuste en el mayor)."""
    labels = {k: lab for k, lab in MAGYP_PRODUCTS}
    order = [k for k, _ in MAGYP_PRODUCTS]
    if rosario <= 0:
        return [{"product": k, "label": labels[k], "camiones": 0} for k in order]
    if national_total <= 0:
        # Sin total nacional: todo en soja (fallback)
        out = [{"product": k, "label": labels[k], "camiones": 0} for k in order]
        out[order.index("soja")]["camiones"] = rosario
        return out
    scale = rosario / national_total
    raw = {k: national_products.get(k, 0) * scale for k in order}
    rounded = {k: int(round(v)) for k, v in raw.items()}
    diff = rosario - sum(rounded.values())
    if diff != 0:
        # Ajustar el producto con mayor conteo (o soja si empate/cero)
        pivot = max(order, key=lambda k: (rounded[k], raw[k], k == "soja"))
        rounded[pivot] = max(0, rounded[pivot] + diff)
        # Si el ajuste dejó suma incorrecta por clamp, repartir en otro
        diff2 = rosario - sum(rounded.values())
        if diff2 != 0:
            for k in sorted(order, key=lambda x: -rounded[x]):
                if k == pivot:
                    continue
                rounded[k] = max(0, rounded[k] + diff2)
                break
    return [{"product": k, "label": labels[k], "camiones": rounded[k]} for k in order]


def parse_magyp_trucks_html(html: str, *, source_url: str = MAGYP_TRUCKS_URL) -> dict[str, Any]:
    """Parse MAGyP daily trucks HTML table into trucks.json schema."""
    rows = _MagypTableParser().feed(html)
    page_year: int | None = None
    page_month: int | None = None
    for row in rows:
        for cell in row:
            my = _parse_month_year_header(cell)
            if my:
                page_year, page_month = my
                break
        if page_year:
            break
    if not page_year or not page_month:
        raise ValueError("MAGyP trucks: no se encontró cabecera de mes/año")

    day_rows: list[dict[str, Any]] = []
    for row in rows:
        if len(row) < 14:
            continue
        date_iso = _parse_day_cell(row[0], page_year, page_month)
        if not date_iso:
            continue
        rosario = _parse_magyp_int(row[1])
        darsena = _parse_magyp_int(row[2])
        necochea = _parse_magyp_int(row[3])
        bb = _parse_magyp_int(row[4])
        zones_total = _parse_magyp_int(row[5])
        products = {
            "trigo": _parse_magyp_int(row[6]),
            "maiz": _parse_magyp_int(row[7]),
            "sorgo": _parse_magyp_int(row[8]),
            "cebada": _parse_magyp_int(row[9]),
            "soja": _parse_magyp_int(row[10]),
            "girasol": _parse_magyp_int(row[11]),
        }
        national_total = _parse_magyp_int(row[12])
        vagones = _parse_magyp_int(row[13]) if len(row) > 13 else 0
        day_rows.append(
            {
                "date": date_iso,
                "rosario": rosario,
                "darsena": darsena,
                "necochea": necochea,
                "bahia_blanca": bb,
                "zones_total": zones_total,
                "products": products,
                "national_total": national_total,
                "vagones": vagones,
                "date_cell": row[0],
            }
        )

    if not day_rows:
        raise ValueError("MAGyP trucks: sin filas diarias parseables")

    day_rows.sort(key=lambda r: r["date"])
    chosen = None
    for row in reversed(day_rows):
        if row["rosario"] > 0:
            chosen = row
            break
    if chosen is None:
        raise ValueError("MAGyP trucks: ninguna fila con Rosario > 0")

    by_product = _scale_products_to_rosario(
        chosen["products"], chosen["rosario"], chosen["national_total"]
    )
    by_product_map = {p["product"]: p["camiones"] for p in by_product}

    # history_7d: últimos 7 días de la tabla hasta la fecha elegida (incluye ceros)
    hist_candidates = [r for r in day_rows if r["date"] <= chosen["date"]]
    hist_slice = hist_candidates[-7:]
    history_7d = [{"date": r["date"], "camiones": r["rosario"]} for r in hist_slice]

    payload: dict[str, Any] = {
        "updated_at": ar_tz_now().isoformat(),
        "date": chosen["date"],
        "source": "magyp",
        "source_url": source_url,
        "source_note": (
            "Rosario y aledaños (MAGyP). Mix por producto prorrateado del total nacional del día."
        ),
        "unit": "camiones",
        "total_camiones": chosen["rosario"],
        "total_tn": None,
        "by_product": by_product,
        "by_zone": [
            {
                "zone": "Rosario y aledaños",
                "camiones": chosen["rosario"],
                "by_product": by_product_map,
            }
        ],
        "history_7d": history_7d,
        "national_total": chosen["national_total"],
        "raw": {
            "page_month": f"{page_year}-{page_month:02d}",
            "date_cell": chosen["date_cell"],
            "zones": {
                "rosario": chosen["rosario"],
                "darsena": chosen["darsena"],
                "necochea": chosen["necochea"],
                "bahia_blanca": chosen["bahia_blanca"],
                "zones_total": chosen["zones_total"],
            },
            "national_products": chosen["products"],
            "vagones": chosen["vagones"],
            "days_parsed": len(day_rows),
            # National camiones by product for each day on the page (stock ledger).
            "national_days": [
                {
                    "date": r["date"],
                    "products": dict(r["products"]),
                    "national_total": r["national_total"],
                    "rosario": r["rosario"],
                }
                for r in day_rows
                if str(r["date"]).startswith(f"{page_year}-{page_month:02d}")
            ],
        },
    }
    return payload


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
        "source_note": "Muestra realista (seed). Ejecutar refresh intenta MAGyP; si falla se conserva este JSON.",
        "unit": "camiones",
        "total_camiones": sum(p["camiones"] for p in by_product),
        "total_tn": sum(p["tn"] for p in by_product),
        "by_product": by_product,
        "by_zone": by_zone,
        "history_7d": _history_7d(today),
    }


def try_fetch_trucks(*, timeout: int = 45) -> dict[str, Any] | None:
    """Fetch+parse MAGyP daily trucks table. Returns None on failure (keep previous)."""
    import urllib.error
    import urllib.request

    url = MAGYP_TRUCKS_URL
    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "cola-buques-rosario/1.0",
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "es-AR,es;q=0.9",
            },
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            charset = resp.headers.get_content_charset() or "utf-8"
        html = raw.decode(charset, errors="replace")
        payload = parse_magyp_trucks_html(html, source_url=url)
        print(
            f"OK MAGyP trucks date={payload['date']} "
            f"rosario={payload['total_camiones']} national={payload.get('national_total')}"
        )
        return payload
    except Exception as ex:
        print(f"FAIL MAGyP trucks scrape: {ex}", file=sys.stderr)
        return None


def build_vessels_payload(
    vessels: list[dict[str, Any]],
    meta: dict[str, Any],
    *,
    live: bool,
    sailed_ok: bool,
) -> dict[str, Any]:
    vessels = [enrich_vessel_destination(dict(v)) for v in vessels]
    up = [v for v in vessels if v.get("up_river")]
    inferred_n = sum(1 for v in up if v.get("destination_source") == "inferred")
    return {
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
            "dest_inferred": inferred_n,
        },
        "vessels": vessels,
    }


def refresh_vessels(
    data_dir: Path | None = None,
    *,
    write_sample: bool = True,
    download_sailed: bool = True,
    timeout: int = 45,
) -> dict[str, Any]:
    """Download NABSA PDF, parse lineup, write vessels.json under data_dir.

    Returns the vessels payload. Raises on hard failure (no parse and no sample).
    """
    data_dir = Path(data_dir) if data_dir else DATA
    data_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = data_dir / "vessel_update.pdf"

    # Bounded download timeout for server-side use
    def _download(url: str, dest: Path) -> bool:
        try:
            r = requests.get(
                url,
                timeout=timeout,
                headers={"User-Agent": "cola-buques-rosario/1.0"},
            )
            r.raise_for_status()
            dest.write_bytes(r.content)
            print(f"OK download {url} -> {dest.name} ({len(r.content)} bytes)")
            return True
        except Exception as ex:
            print(f"FAIL download {url}: {ex}", file=sys.stderr)
            return False

    live = _download(VESSEL_URL, pdf_path)
    sailed_ok = False
    sailed_pdf_path = data_dir / "vessels_sailed_update.pdf"
    if download_sailed:
        sailed_ok = _download(SAILED_URL, sailed_pdf_path)
    # Parse sailed PDF whenever present (fresh download or prior file)
    if sailed_pdf_path.exists():
        try:
            write_sailed_month(data_dir, sailed_pdf_path)
        except Exception as sex:
            print(f"WARN sailed_month write failed: {sex}", file=sys.stderr)

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
        sample = data_dir / "sample-vessels.json"
        bundled = DATA / "sample-vessels.json"
        for candidate in (sample, bundled, data_dir / "vessels.json", DATA / "vessels.json"):
            if candidate.exists():
                print(f"Using fallback {candidate}")
                payload = json.loads(candidate.read_text(encoding="utf-8"))
                payload.setdefault("live", False)
                payload["parse_ok"] = payload.get("parse_ok", False)
                (data_dir / "vessels.json").write_text(
                    json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                return payload
        raise RuntimeError("No vessels data available")

    payload = build_vessels_payload(vessels, meta, live=live, sailed_ok=sailed_ok)
    (data_dir / "vessels.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    if write_sample:
        try:
            (data_dir / "sample-vessels.json").write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except OSError:
            pass
    up_n = payload["counts"]["up_river"]
    print(f"Wrote {data_dir}/vessels.json (up_river={up_n})")
    return payload



STOCK_LEDGER_PRODUCTS = ("maiz", "soja", "trigo", "girasol", "sorgo", "cebada")


def _ledger_day_entry(products: dict[str, Any], national_total: int) -> dict[str, int]:
    entry = {k: int(products.get(k) or 0) for k in STOCK_LEDGER_PRODUCTS}
    entry["national_total"] = int(national_total or 0)
    return entry


def update_truck_inflow_ledger(
    data_dir: Path | None,
    trucks: dict[str, Any],
) -> dict[str, Any] | None:
    """Upsert national MAGyP products into truck_inflow_ledger.json.

    Uses raw.national_days (full month table) when present; else raw.national_products
    for trucks.date. Rolls the ledger when the calendar month changes.
    """
    if not trucks or trucks.get("source") not in {"magyp", "sample"}:
        # Still accept magyp-shaped payloads even if source missing.
        raw = trucks.get("raw") if trucks else None
        if not isinstance(raw, dict) or not (
            raw.get("national_products") or raw.get("national_days")
        ):
            return None

    data_dir = Path(data_dir) if data_dir else DATA
    data_dir.mkdir(parents=True, exist_ok=True)
    ledger_path = data_dir / "truck_inflow_ledger.json"

    date_str = str(trucks.get("date") or "").strip()
    if not date_str or len(date_str) < 7:
        print("WARN ledger: trucks.date missing — skip", file=sys.stderr)
        return None
    month = date_str[:7]
    baseline_as_of = f"{month}-01"

    ledger: dict[str, Any]
    if ledger_path.exists():
        try:
            ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
        except Exception:
            ledger = {}
    else:
        # Prefer bundled seed when writable copy missing (Vercel /tmp).
        bundled = DATA / "truck_inflow_ledger.json"
        if bundled.exists() and bundled != ledger_path:
            try:
                ledger = json.loads(bundled.read_text(encoding="utf-8"))
            except Exception:
                ledger = {}
        else:
            ledger = {}

    if ledger.get("month") != month:
        ledger = {
            "month": month,
            "baseline_as_of": baseline_as_of,
            "days": {},
            "updated_at": ar_tz_now().isoformat(),
        }
    else:
        ledger.setdefault("month", month)
        ledger.setdefault("baseline_as_of", baseline_as_of)
        ledger.setdefault("days", {})

    days: dict[str, Any] = dict(ledger.get("days") or {})
    raw = trucks.get("raw") or {}
    national_days = raw.get("national_days") or []
    upserted = 0
    if isinstance(national_days, list) and national_days:
        for row in national_days:
            if not isinstance(row, dict):
                continue
            d_iso = str(row.get("date") or "").strip()
            if not d_iso or not d_iso.startswith(month):
                continue
            products = row.get("products") or {}
            days[d_iso] = _ledger_day_entry(products, int(row.get("national_total") or 0))
            upserted += 1
    else:
        products = raw.get("national_products") or {}
        if products:
            days[date_str] = _ledger_day_entry(
                products, int(trucks.get("national_total") or 0)
            )
            upserted = 1

    if upserted == 0:
        print("WARN ledger: no national products to upsert", file=sys.stderr)
        return ledger if ledger.get("days") else None

    ledger["days"] = dict(sorted(days.items()))
    ledger["updated_at"] = ar_tz_now().isoformat()
    ledger_path.write_text(
        json.dumps(ledger, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        f"Wrote {ledger_path} month={month} days={len(ledger['days'])} "
        f"(upserted={upserted})"
    )
    return ledger


def ensure_trucks(
    data_dir: Path | None = None,
    *,
    write_sample: bool = True,
    timeout: int = 45,
) -> dict[str, Any]:
    """Refresh trucks from MAGyP. On success write trucks.json (+ sample). On failure keep previous."""
    data_dir = Path(data_dir) if data_dir else DATA
    data_dir.mkdir(parents=True, exist_ok=True)
    trucks_path = data_dir / "trucks.json"
    live_trucks = try_fetch_trucks(timeout=timeout)
    if live_trucks:
        blob = json.dumps(live_trucks, ensure_ascii=False, indent=2)
        trucks_path.write_text(blob, encoding="utf-8")
        if write_sample:
            try:
                (data_dir / "sample-trucks.json").write_text(blob, encoding="utf-8")
            except OSError as ex:
                print(f"WARN could not write sample-trucks.json: {ex}", file=sys.stderr)
        print(f"Wrote {trucks_path} (source=magyp date={live_trucks.get('date')})")
        try:
            update_truck_inflow_ledger(data_dir, live_trucks)
        except Exception as lex:
            print(f"WARN ledger update failed: {lex}", file=sys.stderr)
        return live_trucks

    # Failure: never silently pretend seed is live.
    if trucks_path.exists():
        prev = json.loads(trucks_path.read_text(encoding="utf-8"))
        src = prev.get("source", "?")
        print(
            f"MAGyP trucks scrape failed — keeping previous trucks.json "
            f"(source={src} date={prev.get('date')})",
            file=sys.stderr,
        )
        try:
            update_truck_inflow_ledger(data_dir, prev)
        except Exception as lex:
            print(f"WARN ledger update (prev) failed: {lex}", file=sys.stderr)
        return prev

    for candidate in (DATA / "trucks.json", DATA / "sample-trucks.json"):
        if candidate.exists() and candidate != trucks_path:
            text = candidate.read_text(encoding="utf-8")
            trucks_path.write_text(text, encoding="utf-8")
            print(f"MAGyP trucks scrape failed — seeded from {candidate.name}", file=sys.stderr)
            return json.loads(text)

    seed = seed_trucks()
    blob = json.dumps(seed, ensure_ascii=False, indent=2)
    trucks_path.write_text(blob, encoding="utf-8")
    if write_sample:
        try:
            (data_dir / "sample-trucks.json").write_text(blob, encoding="utf-8")
        except OSError:
            pass
    print("MAGyP trucks scrape failed — wrote seed trucks.json (source=sample)", file=sys.stderr)
    return seed


def main() -> int:
    DATA.mkdir(parents=True, exist_ok=True)
    try:
        refresh_vessels(DATA, write_sample=True, download_sailed=True)
    except Exception as ex:
        print(f"Vessels refresh failed: {ex}", file=sys.stderr)
        return 1
    ensure_trucks(DATA)
    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
