"""Offline tests for Williams .xls trucks source (fixtures, no network)."""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

import refresh_data as rd
import williams_trucks as wt

FX = Path(__file__).parent / "fixtures" / "williams"


def _blob(iso: str) -> bytes:
    return (FX / f"{iso}.xls").read_bytes()


def _fake_fetch(available: set[str]):
    def fetch(url: str, timeout: int):
        iso = url.rsplit("/", 1)[-1].removesuffix(".xls")
        return _blob(iso) if iso in available else None
    return fetch


def test_parse_2310_matches_magyp():
    p = wt.parse_williams_xls(_blob("2026-10-23"))
    assert p["date"] == "2026-10-23"
    z = p["zones"]
    assert z["rosario"]["total"] == 4744
    assert z["darsena"]["total"] == 151
    assert z["necochea"]["total"] == 542
    assert z["bahia_blanca"]["total"] == 1228
    assert p["national"]["total"] == 6665
    np_ = p["national"]["products"]
    assert np_["soja"] == 2618 and np_["maiz"] == 2659 and np_["trigo"] == 1153
    assert np_["sorgo"] == 79 and np_["cebada"] == 107 and np_["girasol"] == 49
    assert z["rosario"]["products"]["soja"] == 2171


@pytest.mark.parametrize("iso", ["2026-10-24", "2026-10-26", "2026-10-29"])
def test_parse_zone_sum_equals_national(iso):
    p = wt.parse_williams_xls(_blob(iso))
    assert p["date"] == iso
    assert sum(z["total"] for z in p["zones"].values()) == p["national"]["total"]
    ros = p["zones"]["rosario"]
    assert sum(ros["products"].values()) <= ros["total"]


def test_fallback_previous_days_on_404():
    days = wt.fetch_williams_days(
        date(2026, 10, 30), lookback_days=10,
        fetch=_fake_fetch({"2026-10-23", "2026-10-26", "2026-10-29"}),
    )
    assert sorted(days) == ["2026-10-23", "2026-10-26", "2026-10-29"]


def test_build_payload_schema_and_magyp_gap_fill():
    wdays = wt.fetch_williams_days(
        date(2026, 10, 30), fetch=_fake_fetch({"2026-10-26", "2026-10-29"}),
    )
    magyp = {
        "date": "2026-10-23", "source": "magyp",
        "raw": {"vagones": 153, "national_days": [
            {"date": "2026-10-23", "products": {"soja": 2618}, "national_total": 6665, "rosario": 4744},
            {"date": "2026-10-22", "products": {}, "national_total": 6681, "rosario": 4764},
        ]},
    }
    out = wt.build_trucks_payload(wdays, magyp, now_iso="2026-10-30T10:15:00-03:00")
    for k in ("updated_at", "date", "source", "source_url", "source_note", "unit",
              "total_camiones", "total_tn", "by_product", "by_zone", "history_7d",
              "national_total", "raw"):
        assert k in out
    assert out["source"] == "williams"
    assert "Fuente: Williams Agroservicios" in out["source_note"]
    assert out["date"] == "2026-10-29"
    assert out["total_camiones"] == 4311 and out["national_total"] == 6004
    assert [p["product"] for p in out["by_product"]] == list(wt.PRODUCTS)
    hist = {h["date"]: h["camiones"] for h in out["history_7d"]}
    assert len(out["history_7d"]) == 7
    assert hist["2026-10-23"] == 4744  # MAGyP fills gap
    assert hist["2026-10-26"] == 1735  # Williams
    srcs = {r["date"]: r["source"] for r in out["raw"]["national_days"]}
    assert srcs["2026-10-22"] == "magyp" and srcs["2026-10-29"] == "williams"


def test_try_fetch_trucks_falls_back_to_magyp(monkeypatch):
    magyp = {"date": "2026-10-23", "source": "magyp", "raw": {}}
    monkeypatch.setattr(rd, "try_fetch_trucks_magyp", lambda timeout=45: magyp)
    out = rd.try_fetch_trucks(williams_fetch=lambda u, t: None)
    assert out is magyp


def test_try_fetch_trucks_prefers_williams(monkeypatch):
    monkeypatch.setattr(rd, "try_fetch_trucks_magyp", lambda timeout=45: None)
    monkeypatch.setattr(rd, "ar_tz_now", lambda: __import__("datetime").datetime(2026, 10, 30, 10, 15))
    out = rd.try_fetch_trucks(williams_fetch=_fake_fetch({"2026-10-29"}))
    assert out["source"] == "williams" and out["date"] == "2026-10-29"


def test_ledger_accepts_williams(tmp_path):
    wdays = wt.fetch_williams_days(date(2026, 10, 30), fetch=_fake_fetch({"2026-10-29"}))
    out = wt.build_trucks_payload(wdays, None, now_iso="x")
    led = rd.update_truck_inflow_ledger(tmp_path, out)
    assert led["days"]["2026-10-29"]["national_total"] == 6004
