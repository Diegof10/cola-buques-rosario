"""Offline tests: monthly rollover of the 1° stock baseline (no network)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import refresh_data as rd

SEP_PRODUCTS = {
    "maiz": 1_000_000, "soja": 2_000_000, "trigo": 300_000,
    "girasol": 40_000, "sorgo": 5_000, "cebada": 60_000,
}


def _w(path: Path, obj) -> None:
    path.write_text(json.dumps(obj), encoding="utf-8")


def _r(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _trucks(date: str, prods: dict[str, int]) -> dict:
    return {
        "source": "magyp",
        "date": date,
        "national_total": sum(prods.values()),
        "raw": {"national_products": prods},
    }


EXIST_HTML = """
<table><tr><td>Para ver años anteriores
  <table class="tabla">
    <tr><th>Mes</th><th>Maiz</th><th>Maiz Flynt o   Plata</th><th>Maiz Pisingallo</th></tr>
    <tr><th>sep-26</th><td>26.570.979</td><td>163.004</td><td>405.982</td></tr>
    <tr><th>oct-26</th><td>25.000.000</td><td>1</td><td>2</td></tr>
  </table>
</td></tr></table>
<table class="tabla"><tr><th>Mes</th><th>Soja</th></tr>
  <tr><th>sep-26</th><td>20.466.643</td></tr><tr><th>oct-26</th><td>18.000.000</td></tr></table>
<table class="tabla"><tr><th>Mes</th><th>Trigo Pan</th><th>Trigo Candeal</th></tr>
  <tr><th>sep-26</th><td>5.046.590</td><td>167.559</td></tr><tr><th>oct-26</th><td>4.000.000</td><td>9</td></tr></table>
<table class="tabla"><tr><th>Mes</th><th>Girasol</th></tr>
  <tr><th>sep-26</th><td>1.561.332</td></tr><tr><th>oct-26</th><td>1.200.000</td></tr></table>
<table class="tabla"><tr><th>Mes</th><th>Ceb. Cervecera</th><th>Ceb. Forrajera</th><th>Ceb. apta para Malteria</th></tr>
  <tr><th>sep-26</th><td>717.116</td><td>322.409</td><td>11.533</td></tr>
  <tr><th>oct-26</th><td>700.000</td><td>300.000</td><td>10.000</td></tr></table>
<table class="tabla"><tr><th>Mes</th><th>Sorgo Granifero</th></tr>
  <tr><th>sep-26</th><td>513.950</td></tr><tr><th>oct-26</th><td>500.000</td></tr></table>
"""


def test_parse_existencias_nested_tables_and_cebada_sum():
    out = rd.parse_magyp_existencias_html(EXIST_HTML)
    assert sorted(out) == ["2026-09", "2026-10"]
    sep = out["2026-09"]
    assert sep["as_of"] == "2026-09-01"
    assert sep["products"] == {
        "maiz": 26570979, "soja": 20466643, "trigo": 5046590,
        "girasol": 1561332, "sorgo": 513950, "cebada": 717116 + 322409 + 11533,
    }
    assert out["2026-10"]["products"]["cebada"] == 1_010_000


def test_parse_existencias_skips_incomplete_month():
    html = EXIST_HTML.replace("<tr><th>oct-26</th><td>500.000</td></tr>", "")
    out = rd.parse_magyp_existencias_html(html)
    assert "2026-10" not in out and "2026-09" in out


def test_update_baseline_adds_missing_never_overwrites(tmp_path, monkeypatch):
    monkeypatch.setattr(rd, "DATA", tmp_path / "no-bundled")
    _w(tmp_path / "existencias_baseline.json", {
        "source_url": "x",
        "months": {"2026-09": {"as_of": "2026-09-01", "products": SEP_PRODUCTS}},
    })
    added = rd.update_existencias_baseline(tmp_path, html=EXIST_HTML)
    assert added == ["2026-10"]
    doc = _r(tmp_path / "existencias_baseline.json")
    assert doc["months"]["2026-09"]["products"] == SEP_PRODUCTS  # hand-loaded kept
    assert doc["months"]["2026-10"]["as_of"] == "2026-10-01"
    assert doc["months"]["2026-10"]["products"]["soja"] == 18_000_000


def test_update_baseline_unparseable_logs_and_skips(tmp_path):
    p = tmp_path / "existencias_baseline.json"
    _w(p, {"months": {"2026-09": {"as_of": "2026-09-01", "products": SEP_PRODUCTS}}})
    before = p.read_text()
    assert rd.update_existencias_baseline(tmp_path, html="<html>mantenimiento</html>") == []
    assert p.read_text() == before


def test_truck_ledger_rollover_archives_previous_month(tmp_path, monkeypatch):
    monkeypatch.setattr(rd, "DATA", tmp_path / "no-bundled")
    rd.update_truck_inflow_ledger(tmp_path, _trucks("2026-09-29", {"maiz": 10, "soja": 5}))
    rd.update_truck_inflow_ledger(tmp_path, _trucks("2026-09-30", {"maiz": 20, "soja": 5}))
    led = rd.update_truck_inflow_ledger(tmp_path, _trucks("2026-10-01", {"maiz": 7}))
    assert led["month"] == "2026-10"
    assert list(led["days"]) == ["2026-10-01"]
    sep = led["history"]["2026-09"]
    assert sorted(sep["days"]) == ["2026-09-29", "2026-09-30"]
    assert sep["baseline_as_of"] == "2026-09-01"
    # Next month roll keeps September too
    led = rd.update_truck_inflow_ledger(tmp_path, _trucks("2026-11-01", {"maiz": 1}))
    assert set(led["history"]) == {"2026-09", "2026-10"}


def test_sailed_history_archives_and_uses_ledger_rows(tmp_path):
    out = tmp_path / "sailed_month.json"
    _w(out, {"month": "2026-09", "products": {"maiz": 999.0}, "rows_in_month": 1})
    rows = [
        {"date": "2026-09-10", "commodity": "maiz", "tons": 100.0},
        {"date": "2026-09-11", "commodity": "soja", "tons": 50.0},
        {"date": "2026-10-01", "commodity": "maiz", "tons": 1.0},
    ]
    hist = rd.build_sailed_month_history(out, "2026-10", rows)
    assert "2026-10" not in hist
    assert hist["2026-09"]["products"]["maiz"] == 100.0  # ledger beats rolling PDF
    assert hist["2026-09"]["products"]["soja"] == 50.0


@pytest.fixture()
def srv(tmp_path, monkeypatch):
    import server

    bundled = tmp_path / "bundled"
    writable = tmp_path / "writable"
    bundled.mkdir()
    writable.mkdir()
    monkeypatch.setattr(server, "BUNDLED_DATA", bundled)
    monkeypatch.setattr(server, "WRITABLE_DATA", writable)
    _w(bundled / "existencias_baseline.json", {
        "source_url": "x",
        "months": {"2026-09": {"as_of": "2026-09-01", "products": SEP_PRODUCTS}},
    })
    _w(bundled / "trucks.json", {"source": "magyp", "date": "2026-10-01", "raw": {}})
    _w(writable / "truck_inflow_ledger.json", {
        "month": "2026-10",
        "baseline_as_of": "2026-10-01",
        "days": {"2026-10-01": {"maiz": 10}},
        "history": {"2026-09": {"days": {
            "2026-09-01": {"maiz": 100, "soja": 10, "girasol": 4},
            "2026-09-02": {"maiz": 100},
        }}},
    })
    _w(writable / "sailed_month.json", {
        "month": "2026-10",
        "products": {"maiz": 300.0},
        "history": {"2026-09": {"products": {"maiz": 5000.0, "soja": 100.0}}},
    })
    return server, bundled, writable


def _by_product(payload):
    return {p["product"]: p for p in payload["products"]}


def test_october_uses_provisional_close_of_september(srv):
    server, _, _ = srv
    out = server.compute_stocks_estimado()
    assert out["month"] == "2026-10"
    assert out["baseline_as_of"] == "2026-10-01"
    assert out["baseline_kind"] == server.BASELINE_KIND_PROVISORIO
    assert out["baseline_provisional"]["from_month"] == "2026-09"
    p = _by_product(out)
    # Sep close: 1_000_000 + 200×30 − 5000 = 1_001_000
    assert p["maiz"]["baseline_tn"] == 1_001_000
    assert p["soja"]["baseline_tn"] == 2_000_000 + 10 * 30 - 100
    assert p["girasol"]["baseline_tn"] == 40_000 + 4 * 25
    assert p["trigo"]["baseline_tn"] == 300_000
    # October estimate: provisional + 10×30 − 300
    assert p["maiz"]["estimado_tn"] == 1_001_000 + 300 - 300


def test_official_october_replaces_provisional(srv):
    server, _, writable = srv
    doc = _r(server.BUNDLED_DATA / "existencias_baseline.json")
    oct_products = dict(SEP_PRODUCTS, maiz=777_777)
    doc["months"]["2026-10"] = {"as_of": "2026-10-01", "products": oct_products}
    _w(writable / "existencias_baseline.json", doc)
    out = server.compute_stocks_estimado()
    assert out["baseline_kind"] == server.BASELINE_KIND_OFICIAL
    assert out["baseline_provisional"] is None
    assert _by_product(out)["maiz"]["baseline_tn"] == 777_777


def test_no_history_no_baseline_is_labelled(srv):
    server, _, writable = srv
    led = _r(writable / "truck_inflow_ledger.json")
    led.pop("history")
    _w(writable / "truck_inflow_ledger.json", led)
    out = server.compute_stocks_estimado()
    assert out["baseline_kind"] == "sin baseline"


@pytest.mark.parametrize(
    "header,cell,expected",
    [("Septiembre 2026", "30-sept", "2026-09-30"), ("Octubre 2026", "2-oct", "2026-10-02")],
)
def test_parse_magyp_trucks_month_header(header, cell, expected):
    # Regression: a later _ES_MONTHS redefinition (abbr-only) broke full-name headers.
    row = [cell, "3.867", "208", "718", "1.287", "6.080", "914", "2.499", "121", "39",
           "2.404", "103", "6.080", "234"]
    html = (
        "<table><tr><td>" + header + "</td><td>ZONA</td></tr><tr>"
        + "".join(f"<td>{c}</td>" for c in row) + "</tr></table>"
    )
    out = rd.parse_magyp_trucks_html(html)
    assert out["date"] == expected
    assert out["total_camiones"] == 3867
