"""Unit tests for build_sailed_destinations_ytd and sailed rows ledger."""
from __future__ import annotations

import json
from pathlib import Path

from refresh_data import (
    build_sailed_destinations_ytd,
    ledger_rows_list,
    normalize_dest_key,
    sailed_row_dedupe_key,
    update_sailed_rows_ledger,
)


def _row(date: str, tons: float, destination: str, **extra):
    return {
        "date": date,
        "tons": tons,
        "destination": destination,
        "origin": "ARGENTINA",
        "commodity": "maiz",
        "cargo_raw": "CORN",
        "port": "SAN LORENZO",
        "terminal": "TEST TERMINAL",
        "vessel": "TEST",
        **extra,
    }


def test_normalize_dest_key_basics():
    assert normalize_dest_key("CHINA") == "china"
    assert normalize_dest_key("Argentina") == "ar"
    assert normalize_dest_key("NOT AVAILABLE") is None
    assert normalize_dest_key("") is None
    assert normalize_dest_key("DOMINICAN REPUBLIC") == "dominican repub"
    assert normalize_dest_key("KOREA (REPUBLIC OF SOUTH KOREA)") == "korea"


def test_ytd_aggregates_exports_excludes_argentina_and_sets_through():
    rows = [
        _row("2026-01-15", 1000.0, "CHINA"),
        _row("2026-03-01", 500.5, "CHINA"),
        _row("2026-09-11", 2000.0, "PERU"),
        _row("2026-09-11", 300.0, "ARGENTINA"),
        _row("2026-09-10", 100.0, "NOT AVAILABLE"),
        _row("2026-09-09", 50.0, ""),
        # other year ignored
        _row("2025-12-31", 9999.0, "CHINA"),
    ]
    payload = build_sailed_destinations_ytd(rows, year=2026)

    assert payload["year"] == 2026
    # Honest coverage: min date in ledger, not forced Jan 1
    assert payload["from"] == "2026-01-15"
    assert payload["through"] == "2026-09-11"
    assert payload["coverage_complete_ytd"] is False
    assert payload["unit"] == "t"
    assert payload["ar_tons"] == 300.0
    assert payload["ar_count"] == 1
    assert payload["unknown_tons"] == 150.0
    assert payload["unknown_count"] == 2
    assert payload["rows"] == 6  # excludes 2025 row

    by_key = {e["key"]: e for e in payload["exports"]}
    assert "china" in by_key
    assert by_key["china"]["tons"] == 1500.5
    assert by_key["china"]["count"] == 2
    assert by_key["china"]["label"] == "China"
    assert by_key["peru"]["tons"] == 2000.0
    assert "ar" not in by_key
    assert "argentina" not in by_key

    # Argentina not in export pie total
    assert payload["total_export_tons"] == 3500.5
    # exports sorted by tons desc
    assert payload["exports"][0]["key"] == "peru"
    assert "ledger" in (payload.get("note") or "").lower() or "rolling" in (
        payload.get("note") or ""
    ).lower()


def test_ytd_through_from_max_date_when_year_inferred():
    rows = [
        _row("2026-02-01", 10.0, "INDIA"),
        _row("2026-08-20", 20.0, "INDIA"),
    ]
    payload = build_sailed_destinations_ytd(rows)
    assert payload["year"] == 2026
    assert payload["from"] == "2026-02-01"
    assert payload["through"] == "2026-08-20"
    assert payload["exports"][0]["key"] == "india"
    assert payload["exports"][0]["tons"] == 30.0


def test_ytd_from_is_jan1_only_when_jan1_data_exists():
    rows = [
        _row("2026-01-01", 100.0, "CHINA"),
        _row("2026-06-01", 50.0, "PERU"),
    ]
    payload = build_sailed_destinations_ytd(rows, year=2026)
    assert payload["from"] == "2026-01-01"
    assert payload["coverage_complete_ytd"] is True


def test_ytd_excludes_non_grain_cargo():
    rows = [
        _row("2026-09-01", 1000.0, "CHINA", commodity="soja", cargo_raw="SOYA BEAN"),
        _row("2026-09-03", 45000.0, "CHINA", commodity="otro", cargo_raw="IRON ORE"),
        _row("2026-09-04", 500.0, "PERU", commodity="maiz", cargo_raw="CORN"),
        _row("2026-09-05", 7000.0, "PERU", commodity="otro", cargo_raw="MALT"),
    ]
    payload = build_sailed_destinations_ytd(rows, year=2026)
    assert payload.get("grains_only") is True
    by_key = {e["key"]: e for e in payload["exports"]}
    assert by_key["china"]["tons"] == 1000.0
    assert by_key["china"]["count"] == 1
    assert by_key["peru"]["tons"] == 500.0
    assert payload["ignored_non_grain_tn"] == 52000.0
    assert payload["ignored_non_grain_count"] == 2
    assert payload["total_export_tons"] == 1500.0


def test_sailed_row_dedupe_key_stable():
    a = _row("2026-09-01", 16999.86, "CONGO", vessel="MALLIKA NAREE")
    b = _row("2026-09-01", 16999.86, "CONGO", vessel="mallika naree")
    assert sailed_row_dedupe_key(a) == sailed_row_dedupe_key(b)
    c = _row("2026-09-01", 16999.86, "CONGO", vessel="OTHER")
    assert sailed_row_dedupe_key(a) != sailed_row_dedupe_key(c)


def test_ledger_upsert_dedupes_and_accumulates_months(tmp_path: Path):
    """First PDF (Sep) then another batch (Aug) → ledger grows; YTD spans both months."""
    sep_rows = [
        _row("2026-09-01", 1000.0, "CHINA", vessel="A"),
        _row("2026-09-02", 500.0, "PERU", vessel="B"),
        _row("2026-09-01", 1000.0, "CHINA", vessel="A"),  # dup
    ]
    ledger1 = update_sailed_rows_ledger(tmp_path, sep_rows, year=2026)
    assert ledger1["year"] == 2026
    assert ledger1["row_count"] == 2

    aug_rows = [
        _row("2026-08-15", 2000.0, "CHINA", vessel="C"),
        _row("2026-09-01", 1000.0, "CHINA", vessel="A"),  # already present
    ]
    ledger2 = update_sailed_rows_ledger(tmp_path, aug_rows, year=2026)
    assert ledger2["row_count"] == 3

    rows = ledger_rows_list(ledger2)
    ytd = build_sailed_destinations_ytd(rows, year=2026)
    assert ytd["from"] == "2026-08-15"
    assert ytd["through"] == "2026-09-02"
    by_key = {e["key"]: e for e in ytd["exports"]}
    assert by_key["china"]["tons"] == 3000.0  # 1000+2000, not double-counting Sep dup
    assert by_key["peru"]["tons"] == 500.0

    # Persisted on disk
    raw = json.loads((tmp_path / "sailed_rows_ledger.json").read_text(encoding="utf-8"))
    assert raw["row_count"] == 3
    assert isinstance(raw["rows"], dict)


def test_ledger_rolls_on_year_change(tmp_path: Path):
    update_sailed_rows_ledger(
        tmp_path, [_row("2025-12-01", 100.0, "CHINA")], year=2025
    )
    ledger = update_sailed_rows_ledger(
        tmp_path, [_row("2026-01-10", 50.0, "PERU")], year=2026
    )
    assert ledger["year"] == 2026
    assert ledger["row_count"] == 1
    only = ledger_rows_list(ledger)[0]
    assert only["date"] == "2026-01-10"
